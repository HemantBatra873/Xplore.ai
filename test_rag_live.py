import sys

import httpx

BASE_URL = "http://localhost:8000/api/v1"


def main():
    print("=== Starting RAG live end-to-end test ===")

    print("\n1. Signing in to obtain a JWT token...")
    login_data = {
        "username": "admin@example.com",
        "password": "password123",
    }

    with httpx.Client() as client:
        response = client.post(f"{BASE_URL}/auth/login", data=login_data)
        if response.status_code != 200:
            print("   Login failed, registering a test user first...")
            reg_response = client.post(
                f"{BASE_URL}/users/",
                json={
                    "username": "admin",
                    "email": "admin@example.com",
                    "password": "password123",
                    "full_name": "Test Admin",
                },
            )
            if reg_response.status_code not in (200, 201):
                print(f"   Registration failed: {reg_response.text}")
                sys.exit(1)
            response = client.post(f"{BASE_URL}/auth/login", data=login_data)

        token_info = response.json()
        access_token = token_info.get("access_token")
        if not access_token:
            print(f"   Unable to obtain a token: {token_info}")
            sys.exit(1)

        print("   Token acquired.")

        headers = {"Authorization": f"Bearer {access_token}"}

        print("\n2. Uploading a knowledge document...")
        file_path = "README.md"
        try:
            with open(file_path, "rb") as f:
                files = {"file": ("README.md", f, "text/markdown")}
                upload_resp = client.post(
                    f"{BASE_URL}/rag/upload", headers=headers, files=files
                )

            if upload_resp.status_code in (200, 201, 202):
                upload_data = upload_resp.json()
                print(
                    f"   Upload accepted. Document ID: {upload_data['id']}, "
                    f"chunks: {upload_data.get('chunks_count')}"
                )
            else:
                print(f"   Upload failed: {upload_resp.text}")
                sys.exit(1)
        except Exception as e:
            print(f"   Failed to read file: {e}")
            sys.exit(1)

        print("\n3. Running a RAG knowledge-base query...")
        query_text = "What is Xplore.ai and what core capabilities does it provide?"
        print(f"   Question: {query_text}")

        query_payload = {"query": query_text, "top_k": 2}
        query_resp = client.post(
            f"{BASE_URL}/rag/query",
            headers=headers,
            json=query_payload,
            timeout=120.0,
        )

        if query_resp.status_code == 200:
            result = query_resp.json()
            print("\n   AI answer:")
            print("-" * 50)
            print(result["answer"])
            print("-" * 50)
            print("\n   Retrieved source passages:")
            for idx, chunk in enumerate(result["source_chunks"], 1):
                print(f"     Passage {idx}: {chunk.strip()}")
            print("\nEnd-to-end RAG test completed successfully.")
        else:
            print(f"   Query failed: {query_resp.text}")


if __name__ == "__main__":
    main()
