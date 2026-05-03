import argparse
import subprocess
import json
import sys
import os

def main():
    parser = argparse.ArgumentParser(description="Python wrapper for Curate.ai API via Rust backend")
    parser.add_argument("--operation", choices=["transform", "getUsage"], required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--task")
    parser.add_argument("--schema")
    parser.add_argument("--docs-file")

    args = parser.parse_args()

    # Build input payload for Rust
    rust_input = {
        "operation": args.operation,
        "baseUrl": args.url,
        "token": args.token,
        "payload": None
    }

    if args.operation == "transform":
        if not args.task or not args.schema or not args.docs_file:
            print(json.dumps({"error": "transform operation requires --task, --schema, and --docs-file"}))
            sys.exit(1)
        
        try:
            with open(args.docs_file, 'r', encoding='utf-8') as f:
                documents = json.load(f)
        except Exception as e:
            print(json.dumps({"error": f"Failed to read docs-file: {str(e)}"}))
            sys.exit(1)

        rust_input["payload"] = {
            "task": args.task,
            "schema": args.schema,
            "documents": documents
        }

    # Path to the compiled Rust binary
    script_dir = os.path.dirname(os.path.abspath(__file__))
    rust_bin = os.path.join(script_dir, "curate-cli", "target", "release", "curate-cli")

    if not os.path.exists(rust_bin):
        print(json.dumps({"error": f"Rust binary not found at {rust_bin}. Please run 'cargo build --release' in curate-cli folder."}))
        sys.exit(1)

    try:
        process = subprocess.run(
            [rust_bin],
            input=json.dumps(rust_input),
            text=True,
            capture_output=True,
            check=False
        )

        # Output whatever the rust binary outputted. It should be JSON.
        if process.stdout:
            print(process.stdout.strip())
            
        if process.returncode != 0:
            if not process.stdout and process.stderr:
                print(json.dumps({"error": process.stderr.strip()}))
            sys.exit(process.returncode)
            
    except Exception as e:
        print(json.dumps({"error": f"Failed to execute Rust binary: {str(e)}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
