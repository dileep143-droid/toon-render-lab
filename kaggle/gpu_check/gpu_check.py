import subprocess, sys
print("PYTHON", sys.version)
print(subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout or "no nvidia-smi")
try:
    import torch
    print("TORCH", torch.__version__, "CUDA", torch.cuda.is_available(), torch.cuda.device_count(),
          [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])
except Exception as ex:
    print("torch error", ex)
