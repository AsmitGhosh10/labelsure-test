from typing import Any 
import numpy as np

def to_python_float(value: Any) -> Any:
      """
            #### Convert numpy types to native python float types
      """
      if value is None:
            return None
      if isinstance(value, np.generic):
            return value.item()
      
      return float(value)

def clean_numpy(obj : Any) -> Any:
      """
            Recursively convert numpy types in dict/list structures.
      """
      if isinstance(obj, dict):
            return {k : clean_numpy(v) for k, v in obj.items()}
      elif isinstance(obj, list):
            return [clean_numpy(v) for v in obj]
      elif isinstance(obj, np.generic):
            return obj.item()
      
      return obj
      