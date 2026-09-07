import structlog
import logging
import os
from .config import settings

def setup_logging():
      """Config structures JSON logging"""

      log_file_path = os.path.join("logs", "app.log")
      os.makedirs("logs", exist_ok=True)

      timestamper = structlog.processors.TimeStamper(fmt="%H:%M:%S")

      def color(text: str, code : str) -> str:
            RESET = "\033[0m"
            return f"{code}{text}{RESET}"
      
      COLORS = {
            "grey": "\033[90m",
            "green": "\033[32m",
            "yellow": "\033[33m",
            "red": "\033[31m",
            "bold_red": "\033[1;31m",
            "blue": "\033[34m",
            "white": "\033[37m",
      }     
      
      # ==== 🎨 Custom level styling ====
      def add_emoji(_, __, event_dict):
            level =event_dict.get("level", event_dict.get("level_name", "")).lower()

            emoji_map = {
                  "debug" : "🔍",
                  "info" : "✨",
                  "warning" : "⚠️",
                  "error" : "❌",
                  "critical" : "🔥"
            }

            event_dict["level_display"] = f"{emoji_map.get(level, '')}  {level.upper()}"
            event_dict["raw_level"] = level.upper()

            return event_dict

      def get_color_level(level : str):
            return {
                  "DEBUG": COLORS["grey"],
                  "INFO": COLORS["green"],
                  "WARNING": COLORS["yellow"],
                  "ERROR": COLORS["red"],
                  "CRITICAL": COLORS["bold_red"],
            }.get(level, COLORS["white"])
      
      def custom_console_renderer(_, __, event_dict):
            ts = event_dict.get("timestamp", "")
            level_display = event_dict.get("level_display", "")
            raw_level = event_dict.get("raw_level", "INFO")
            logger = event_dict.get("logger", "")
            msg = event_dict.get("event", "")

            # === Apply colors ===
            level_colored = color(level_display, get_color_level(raw_level))
            ts_colored = color(ts, COLORS["grey"])
            logger_colored = color(logger, COLORS["blue"])
            msg_colored = color(msg, COLORS["white"])

            return f"{level_colored} | {ts_colored} | {logger_colored} | {msg_colored}"
      
      def clean_event_dict(_, __, event_dict):
            event_dict.pop("level", None)
            return event_dict
      
      shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            add_emoji,
            timestamper,
            clean_event_dict,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
      ]
      structlog.configure(
            processors=shared_processors + [
                  structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
      )

      # Console formatter
      console_formatter = structlog.stdlib.ProcessorFormatter(
            processor=custom_console_renderer,
            foreign_pre_chain=shared_processors,
      )

      # File formatter
      file_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
      )

      # === SETUP HANDLERS ===
      console_handler = logging.StreamHandler()
      console_handler.setFormatter(console_formatter)

      file_handler = logging.FileHandler(log_file_path)
      file_handler.setFormatter(file_formatter)

      #Root logger
      root_logger = logging.getLogger()
      if not root_logger.handlers:
            root_logger.addHandler(console_handler)
            root_logger.addHandler(file_handler)

      root_logger.setLevel(settings.LOG_LEVEL)
      
      # ==== Reduce Noise from libraries ====
      logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
      logging.getLogger("sqlalchemy.engine").propagate = False

      logging.getLogger("transformers").setLevel(logging.ERROR)
      logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
      logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
      
      logging.getLogger("httpx").setLevel(logging.WARNING)
      logging.getLogger("httpcore").setLevel(logging.WARNING)

      logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
      for name in ["uvicorn", "uvicorn.error"]:
            uv_logger = logging.getLogger(name)
            uv_logger.handlers = []
            uv_logger.propagate = True

      logging.getLogger("app.ml.retrieval").setLevel(logging.DEBUG)
      #Uvicorn access logs
      # logging.getLogger("uvicorn.access").handlers = []


      