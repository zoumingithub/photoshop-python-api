from flask import Flask, request, jsonify
from photoshop import Session
import os
import oss2
from dotenv import load_dotenv
from typing import Tuple, List, Dict

load_dotenv()

app = Flask(__name__)

# Get OSS configuration from environment variables
OSS_ENDPOINT = os.environ.get('OSS_ENDPOINT')
OSS_BUCKET_NAME = os.environ.get('OSS_BUCKET_NAME')
OSS_ACCESS_KEY_ID = os.environ.get('OSS_ACCESS_KEY_ID')
OSS_ACCESS_KEY_SECRET = os.environ.get('OSS_ACCESS_KEY_SECRET')

# Validate OSS configuration
if not all([OSS_ENDPOINT, OSS_BUCKET_NAME, OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET]):
    raise ValueError("Missing required OSS environment variables")

PSD_DIRECTORY = r"C:\Users\Administrator\photoshop-python-api"

def process_psd_updates(psd_path: str, jpg_path: str, text_updates: List[Dict]) -> Tuple[List[str], List[Dict], bool]:
    """
    Core function to process PSD text updates
    
    Args:
        psd_path: Path to the PSD file
        jpg_path: Path where the JPG should be saved
        text_updates: List of updates containing layer_id and text
        
    Returns:
        Tuple containing:
        - List of successfully updated layer IDs
        - List of failed layer updates with error messages
        - Boolean indicating if any updates were successful
    """
    updated_layers = []
    failed_layers = []

    with Session() as ps:
        # Open PSD file
        ps.app.open(psd_path)
        doc = ps.active_document

        # Update text in specified layers
        for update in text_updates:
            if not isinstance(update, dict) or 'layer_id' not in update or 'text' not in update:
                failed_layers.append({'error': 'Invalid update format'})
                continue

            layer_id = update['layer_id']
            new_text = update['text']

            try:
                layer = doc.artLayers.getByName(layer_id)
                
                if layer.kind == ps.LayerKind.TextLayer:
                    layer.textItem.contents = new_text
                    updated_layers.append(layer_id)
                else:
                    failed_layers.append({
                        'layer_id': layer_id,
                        'error': 'Not a text layer'
                    })
            except Exception as e:
                failed_layers.append({
                    'layer_id': layer_id,
                    'error': str(e)
                })

        if updated_layers:
            # Save as JPG
            options = ps.JPEGSaveOptions(quality=5)
            doc.saveAs(jpg_path, options, asCopy=True)
        
        doc.close()

    return updated_layers, failed_layers, bool(updated_layers)

@app.route('/update-psd-text', methods=['POST'])
def update_psd_text():
    try:
        # Validate request
        data = request.get_json()
        if not data or 'psd_id' not in data or 'updates' not in data:
            return jsonify({'error': 'Missing psd_id or updates in request'}), 400

        if not isinstance(data['updates'], list):
            return jsonify({'error': 'Updates must be a list of layer updates'}), 400

        # Setup paths
        psd_id = data['psd_id']
        psd_path = os.path.join(PSD_DIRECTORY, f"{psd_id}.psd")
        jpg_path = os.path.join(PSD_DIRECTORY, f"{psd_id}_output.jpg")

        if not os.path.exists(psd_path):
            return jsonify({'error': 'PSD file not found'}), 404

        # Process PSD updates
        updated_layers, failed_layers, success = process_psd_updates(
            psd_path, jpg_path, data['updates']
        )

        if not success:
            return jsonify({
                'error': 'No layers were updated',
                'failed_layers': failed_layers
            }), 400

        # Upload to OSS
        auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
        bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET_NAME)
        oss_path = f'psd-outputs/{psd_id}_output.jpg'
        
        with open(jpg_path, 'rb') as f:
            bucket.put_object(oss_path, f)

        oss_url = f'https://{OSS_BUCKET_NAME}.{OSS_ENDPOINT}/{oss_path}'

        # Clean up
        os.remove(jpg_path)

        return jsonify({
            'success': True,
            'message': 'Text updated and file uploaded successfully',
            'updated_layers': updated_layers,
            'failed_layers': failed_layers,
            'oss_path': oss_path,
            'oss_url': oss_url
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def test_psd_processing():
    """Test function for PSD processing"""
    test_psd = "1.psd"  # Make sure this file exists in your PSD_DIRECTORY
    test_updates = [
        {"layer_id": "title", "text": "Test text 1"},
        {"layer_id": "test_layer_2", "text": "Test text 2"},
        {"layer_id": "nonexistent_layer", "text": "Should fail"}
    ]
    
    psd_path = os.path.join(PSD_DIRECTORY, test_psd)
    jpg_path = os.path.join(PSD_DIRECTORY, "test_output.jpg")
    
    try:
        updated_layers, failed_layers, success = process_psd_updates(
            psd_path, jpg_path, test_updates
        )
        
        print("Test Results:")
        print(f"Success: {success}")
        print(f"Updated layers: {updated_layers}")
        print(f"Failed layers: {failed_layers}")
        
        if os.path.exists(jpg_path):
            os.remove(jpg_path)
            print("Test output file cleaned up")
            
        return success
        
    except Exception as e:
        print(f"Test failed with error: {str(e)}")
        return False

if __name__ == '__main__':
    # Run tests if in debug mode
    # if app.debug:
    if True:
        print("Running tests...")
        test_result = test_psd_processing()
        print(f"Tests {'passed' if test_result else 'failed'}")
        
    # app.run(debug=True, port=5000)

