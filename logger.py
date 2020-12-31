import logging

logger = logging.getLogger("szkopul-fabric")
logger.setLevel(logging.INFO)
c_handler = logging.StreamHandler()
c_handler.setLevel(logging.INFO)
logger.addHandler(c_handler)
