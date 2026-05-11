import csv
import os
from datetime import datetime
from typing import Dict
from core.logger import logger

class DataExporter:
    @staticmethod
    def export_csv(counts: Dict[str, Dict[str, int]], output_dir: str = "exports"):
        """Export current vehicle counts to a CSV file."""
        try:
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"traffic_stats_{timestamp}.csv"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Write header
                lines = list(counts.keys())
                header = ["Vehicle Type"] + lines
                writer.writerow(header)
                
                # Get all vehicle types
                all_types = set()
                for line in counts:
                    all_types.update(counts[line].keys())
                all_types = sorted(list(all_types))
                
                # Write data rows
                for v_type in all_types:
                    row = [v_type]
                    for line in lines:
                        row.append(counts[line].get(v_type, 0))
                    writer.writerow(row)
                    
            logger.info(f"Data exported successfully to {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Error exporting data: {e}")
            return None
