# -*- coding: utf-8 -*-
"""
/***************************************************************************
 DHIS2DataFetcher
                                 A QGIS plugin
 Fetch Data from DHIS2
                             -------------------
        begin                : 2018-02-14
        copyright            : (C) 2018 by Zuidt
        email                : richard@zuidt.nl
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load DHIS2DataFetcher class from file DHIS2DataFetcher.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .ddf import DHIS2DataFetcher
    return DHIS2DataFetcher(iface)
