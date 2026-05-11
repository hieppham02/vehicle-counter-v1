import json
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Tuple

class LineConfig(BaseModel):
    name: str
    color: Tuple[int, int, int]
    pt1: Tuple[int, int]
    pt2: Tuple[int, int]

class AppConfig(BaseModel):
    model_path: str = Field(default="E:/EAUT/Python/final_test/model/lastest.pt")
    video_dir: str = Field(default="E:/EAUT/Python/final_test/test/")
    confidence_threshold: float = Field(default=0.35)
    iou_threshold: float = Field(default=0.45)
    target_classes: List[int] = Field(default=[0, 1, 2, 3]) # bus, car, motorbike, truck
    counting_lines: List[LineConfig] = Field(default=[
        LineConfig(name="", color=(255, 0, 0), pt1=(0, 400), pt2=(1000, 400))
    ])
    hide_counted: bool = Field(default=False)
    
    @classmethod
    def load(cls, config_path: str = "configs/app_config.json") -> 'AppConfig':
        path = Path(config_path)
        if not path.exists():
            # Create default config if not exists
            default_config = cls()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(default_config.model_dump_json(indent=4))
            return default_config
            
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return cls(**data)
            
    def save(self, config_path: str = "configs/app_config.json"):
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.model_dump_json(indent=4))

config = AppConfig.load()
