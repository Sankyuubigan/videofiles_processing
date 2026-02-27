import logging
from PySide6.QtCore import QObject, Signal

class QtHandler(QObject, logging.Handler):
    """
    A logging handler that emits a Qt signal for each log record.
    """
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        logging.Handler.__init__(self)
        self.setFormatter(logging.Formatter('%(message)s'))

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)

def setup_logging(log_signal):
    """
    Configures the root logger to use the QtHandler.
    """
    logger = logging.getLogger()
    
    # Очищаем старые обработчики, чтобы логи не дублировались
    if logger.hasHandlers():
        logger.handlers.clear()
        
    # Устанавливаем уровень INFO, чтобы скрыть мусорный DEBUG от yt-dlp
    logger.setLevel(logging.INFO) 
    
    qt_handler = QtHandler()
    qt_handler.log_signal.connect(log_signal)
    logger.addHandler(qt_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(console_handler)
    
    logging.info("Логирование инициализировано.")