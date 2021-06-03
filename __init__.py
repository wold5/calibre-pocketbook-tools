#!/usr/bin/env python
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__ = 'GPL v3'
__copyright__ = '2021, William Ouwehand'
__docformat__ = 'restructuredtext en'

from calibre.customize import InterfaceActionBase

class PocketBookToolsPlugin(InterfaceActionBase):

    name                = 'Pocketbook Tools'
    description         = 'Tools for Pocketbook e-readers.'
    supported_platforms = ['windows', 'osx', 'linux']
    author              = 'William Ouwehand'
    version             = (0, 9, 1)
    minimum_calibre_version = (2, 58, 0)

    actual_plugin = 'calibre_plugins.pocketbook_tools.ui:PocketBookToolsPlugin'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.pocketbook_tools.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()

        # Apply the changes
        ac = self.actual_plugin_
        if ac:
            ac.apply_settings()


if __name__ == '__main__':
    pass
