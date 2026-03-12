import yaml
import json
from pathlib import Path

# Custom dumper to handle Enums and other types by converting to JSON first
def clean_yaml(path):
    print(f"Cleaning {path}...")
    with open(path, 'r', encoding='utf-8') as f:
        # Load with unsafe_load to handle the existing tags
        data = yaml.unsafe_load(f)
    
    # Convert to JSON and back to get rid of Python objects/tags
    # This works because all types in our models are JSON-serializable (or have a string representation)
    # For Enums, we might need a custom encoder or just use json.dumps on the dict if it's already a dict.
    
    # Actually, let's just recursively convert objects to their values/dicts
    def denormalize(obj):
        if isinstance(obj, dict):
            return {k: denormalize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [denormalize(v) for v in obj]
        if hasattr(obj, 'value'): # For Enums
            return obj.value
        return obj

    clean_data = denormalize(data)
    
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(clean_data, f, allow_unicode=True, sort_keys=False)

base_path = Path("services")
for service_dir in base_path.iterdir():
    if service_dir.is_dir():
        kb_path = service_dir / "kb" / "knowledge_base.yaml"
        if kb_path.exists():
            clean_yaml(kb_path)
