import yaml
from pathlib import Path
from core.models import KnowledgeBase

def load_kb(yaml_path: str | Path) -> KnowledgeBase:
    """Загружает базу знаний из YAML-файла и валидирует через Pydantic."""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return KnowledgeBase(**data)

def load_all_kbs(services_dir: str | Path = "services") -> dict[str, KnowledgeBase]:
    """Загружает все базы знаний для каждого сервиса."""
    kbs = {}
    base_path = Path(services_dir)
    for service_dir in base_path.iterdir():
        if service_dir.is_dir():
            kb_path = service_dir / "kb" / "knowledge_base.yaml"
            if kb_path.exists():
                kbs[service_dir.name] = load_kb(kb_path)
    return kbs
