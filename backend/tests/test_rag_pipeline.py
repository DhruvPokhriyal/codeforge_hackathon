import requests
import time
import json

BASE_URL = "http://localhost:8000"

def test_pipeline():
    print("Testing pipeline...")
    
    # 1. Check Protocols (RAG setup)
    try:
        resp = requests.get(f"{BASE_URL}/api/protocols")
        if resp.status_code == 200:
            protocols = resp.json()
            print(f"✅ Protocols found: {len(protocols)} -> {[p['filename'] for p in protocols]}")
        else:
             print(f"❌ Failed to fetch protocols: {resp.status_code}")
    except Exception as e:
        print(f"❌ Error checking protocols: {e}")

    # 2. Upload Audio
    audio_path = "noisy_input/p226_004.wav"
    try:
        with open(audio_path, "rb") as f:
            files = {"file": f}
            print(f"Sending audio: {audio_path}")
            
            start_time = time.time()
            resp = requests.post(f"{BASE_URL}/api/pipeline", files=files)
            duration = time.time() - start_time
            
            if resp.status_code == 200:
                data = resp.json()
                print(f"✅ Pipeline success ({duration:.2f}s)")
                
                # Check RAG results
                chunks = data.get("retrieved_chunks", [])
                if chunks:
                    print(f"✅ Retrieved {len(chunks)} context chunks.")
                    for i, chunk in enumerate(chunks[:2]): # Print first 2
                        print(f"   Chunk {i+1}: {chunk[:100]}...") # Preview
                else:
                    print("⚠️ No chunks retrieved (is RAG working?).")
                
                # Check Plan
                plan = data.get("action_plan", {})
                print(f"📋 Plan Summary: {plan.get('summary', 'No summary')}")
                print(f"📋 Steps: {len(plan.get('steps', []))}")
                
                # Check Request ID for approval
                req_id = data.get("request_id")
                if req_id:
                     print(f"🆔 Request ID: {req_id}")
                     
                     # 3. Approve Plan
                     approve_resp = requests.post(f"{BASE_URL}/api/approve/{req_id}")
                     if approve_resp.status_code == 200:
                         print("✅ Plan approved successfully.")
                     else:
                         print(f"❌ Approval failed: {approve_resp.text}")
                else:
                    print("❌ No request_id returned.")
                    
            else:
                print(f"❌ Pipeline failed: {resp.status_code} - {resp.text}")

    except FileNotFoundError:
        print(f"❌ Audio file not found: {audio_path}")
    except Exception as e:
        print(f"❌ Error during test: {e}")

if __name__ == "__main__":
    test_pipeline()
