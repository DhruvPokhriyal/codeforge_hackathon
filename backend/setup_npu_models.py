#!/usr/bin/env python3
"""
setup_npu_models.py

Utility script to download and export the Gemma 3 1B model into the
correct format for NPU inference (ONNX for Mac ANE, OpenVINO for Intel NPU).

Usage:
  python setup_npu_models.py

Dependencies (install before running):
  pip install optimum[openvino,onnxruntime] transformers
"""

import os
import platform
import subprocess
import sys
from pathlib import Path

MODEL_ID = "google/gemma-3-1b-it"

def run_command(cmd):
    print(f"Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Command failed with error: {e}")
        sys.exit(1)

def check_dependencies():
    try:
        import optimum
    except ImportError:
        print("ERROR: The 'optimum' package is required.")
        print("Please install it: pip install optimum[openvino,onnxruntime] transformers")
        sys.exit(1)

def main():
    check_dependencies()

    base_dir = Path(__file__).parent.resolve()
    models_dir = base_dir / "models"
    models_dir.mkdir(exist_ok=True)

    sys_os = platform.system()

    if sys_os == "Darwin":
        print(f"Detected macOS. Exporting {MODEL_ID} to ONNX format for Apple Neural Engine...")
        out_dir = models_dir / "onnx"
        if out_dir.exists():
            print(f"Directory {out_dir} already exists. Skipping export.")
            return

        # Using optimum-cli to export to ONNX
        cmd = [
            sys.executable, "-m", "optimum.exporters.onnx",
            "--model", MODEL_ID,
            "--task", "text-generation-with-past",
            str(out_dir)
        ]
        run_command(cmd)
        print(f"\n✅ ONNX model successfully exported to: {out_dir}")

    else:
        print(f"Detected {sys_os}. Exporting {MODEL_ID} to OpenVINO IR format for Intel NPU...")
        out_dir = models_dir / "openvino"
        if out_dir.exists():
            print(f"Directory {out_dir} already exists. Skipping export.")
            return

        # Using optimum-cli to export to OpenVINO
        cmd = [
            "optimum-cli", "export", "openvino",
            "--model", MODEL_ID,
            "--task", "text-generation-with-past",
            "--weight-format", "int8", # recommended for NPU
            str(out_dir)
        ]
        run_command(cmd)
        print(f"\n✅ OpenVINO model successfully exported to: {out_dir}")

if __name__ == "__main__":
    main()
