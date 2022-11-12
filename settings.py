import logging


class Settings:
    def __init__(self, root, root_name, verbose_key):
        self.root = root
        self.root_name = root_name

        self.verbose = root.get(verbose_key, False) or None

        logger = logging.getLogger('settings')
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        self.logger = logger

    def get_settings(self, key):
        sub_settings = self.root.get(key)
        return Settings(sub_settings, key, 'verbose')

    def get(self, key, default_value):
        value = self.root.get(key, default_value)

        if self.root_name:
            self.logger.debug("Setting: %s.%s=%s", self.root_name, key, value)
        else:
            self.logger.debug("Setting: %s=%s", key, value)

        return value
