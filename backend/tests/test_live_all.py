import requests
import json
import base64
import os
import time
import glob

BASE_URL = "http://localhost:8000"
NOISY_INPUT_DIR = "/home/ankit/python/codeforge_hackathon/noisy_input"

def test_pipeline():
    print("🚀 Testing pipeline with ALL noisy inputs...")
    
    # Check Inventory
    try:
        resp = requests.get(f"{BASE_URL}/inventory")
        if resp.status_code == 200:
            print(f"✅ Inventory endpoint reachable.")
        else:
             print(f"❌ Failed to fetch inventory: {resp.status_code}")
             return
    except Exception as e:
        print(f"❌ Error checking inventory: {e}")
        return

    # Find Audio Files
    wav_files = sorted(glob.glob(os.path.join(NOISY_INPUT_DIR, "*.wav")))
    if not wav_files:
        print(f"❌ No wav files found in {NOISY_INPUT_DIR}")
        return

    print(f"📂 Found {len(wav_files)} files to process: {[os.path.basename(f) for f in wav_files]}\n")

    for audio_path in wav_files:
        filename = os.path.basename(audio_path)
        print(f"--------------------------------------------------")
        print(f"🎙️ Processing: {filename}")
        
        try:
            with open(audio_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode('utf-8')
                
            payload = {
                "audio_b64": audio_b64,
                "metadata": {"source": "test_script", "filename": filename}
            }
            
            start = time.time()
            
            # PIPELINE
            url = f"{BASE_URL}/pipeline"
            resp = requests.post(url, json=payload)
            duration = time.time() - start
            
            if resp.status_code == 200:
                data = resp.json()
                req_id = data.get("request_id")
                transcript = data.get("transcript", "N/A")
                
                print(f"✅ Request {req_id} (Processed in {duration:.2f}s)")
                print(f"📝 Transcript: \"{transcript}\"")

                situations = data.get("situations", [])
                if situations:
                    # Print Situations
                    for i, sit in enumerate(situations):
                        print(f"   🚩 Situation {i+1}: {sit.get('label')} (Severity Score: {sit.get('severity_score')})")
                        chunks = sit.get("source_chunks", [])
                        if chunks:
                            print(f"      📚 Protocols Found: {len(chunks)} chunks")
                            # print(f"      Excerpt: {chunks[0][:100]}...")
                        else:
                            print(f"      ⚠️ No RAG chunks found.")

                    # APPROVE (Automatically select the first situation)
                    if req_id:
                        print(f"   👍 Auto-approving situation 1...")
                        approve_payload = {
                            "request_id": req_id,
                            "selected_indices": [0]
                        }
                        app_resp = requests.post(f"{BASE_URL}/approve", json=approve_payload)
                        if app_resp.status_code == 200:
                            print("   ✅ Dispatch Confirmed.")
                            q_len = len(app_resp.json().get("queue", []))
                            print(f"   📊 Current Queue Length: {q_len}")
                        else:
                            print(f"   ❌ Approve failed: {app_resp.text}")

                else:
                    print(f"   ⚠️ No situations generated.")

            else:
                print(f"❌ Pipeline failed: {resp.status_code} - {resp.text}")

        except Exception as e:
            print(f"❌ Exception processing {filename}: {e}")

if __name__ == "__main__":
    test_pipeline()
