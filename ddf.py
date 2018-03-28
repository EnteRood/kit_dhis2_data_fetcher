# -*- coding: utf-8 -*-
"""
/***************************************************************************
 DHIS2DataFetcher
                                 A QGIS plugin
 Fetch Data from DHIS2
                              -------------------
        begin                : 2018-02-14
        git sha              : $Format:%H$
        copyright            : (C) 2018 by Zuidt
        email                : richard@zuidt.nl
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from PyQt5.QtCore import QSettings, QTranslator, qVersion, QCoreApplication
from PyQt5.QtGui import QIcon, QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QAction

from qgis.core import QgsMessageLog, Qgis, QgsAuthManager

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .ddf_dialog import DHIS2DataFetcherDialog
from .networkaccessmanager import NetworkAccessManager, RequestsException
import os.path
import json


class DHIS2DataFetcher:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'DHIS2DataFetcher_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Create the dialog (after translation) and keep reference
        self.dlg = DHIS2DataFetcherDialog()

        self.dlg.cb_ou.currentIndexChanged.connect(self.cb_ou_changed)
        self.dlg.cb_pe.currentIndexChanged.connect(self.cb_pe_changed)
        self.dlg.cb_dx.currentIndexChanged.connect(self.cb_dx_changed)
        self.dlg.cb_level.currentIndexChanged.connect(self.cb_level_changed)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&DHIS2 Data Fetcher')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'DHIS2DataFetcher')
        self.toolbar.setObjectName(u'DHIS2DataFetcher')

        self.MSG_TITLE = "DHIS2 datafetcher"

        self.gui_inited = False
        self.nam = None  # created in gui init

        self.ou_items = []
        self.pe_items = []
        self.dx_items = []

        # TODO: coming from GUI
        # for now use playground
        self.username = 'admin'
        self.password = 'district'

        self.analytics_url = ''
        self.level = 2


    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('DHIS2DataFetcher', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def info(self, msg=""):
        QgsMessageLog.logMessage('{}'.format(msg), self.MSG_TITLE, Qgis.Info)

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/DHIS2DataFetcher/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Fetch DHIS2 Data'),
            callback=self.run,
            parent=self.iface.mainWindow())

    def initAuthentication(self):

        # https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/authentication.html#term-authentication-config
        authMgr = QgsAuthManager.instance()
        if authMgr.masterPasswordIsSet():
            msg = 'Authentication master password not recognized'
            assert authMgr.masterPasswordSame("your master password"), msg
        else:
            msg = 'Master password could not be set'
            # The verify parameter check if the hash of the password was
            # already saved in the authentication db
            assert authMgr.setMasterPassword("your master password", verify=True), msg

    def initDropdowns(self):

        self.info('INIT dropdowns')

        # we have to fill drop downs
        # ??? without authentication ???
        # TODO authentications admin/district
        # https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/authentication.html#term-authentication-config
        # TODO: To let a user create a basic authentication via this dialog
        # QgsAuthConfigSelect().show()
        # TODO: zelf een authconfig aanmaken hier op basis van ???
        # TODO: ALS gebruiker dit heeft gedaan, dan achterhalen wat the authid is van zijn/haar config


        self.nam = NetworkAccessManager(authid="dhis2ap", exception_class=RequestsException)


        # ou = Organisational Units
        self.ou_model = QStandardItemModel()
        self.pe_model = QStandardItemModel()
        self.dx_model = QStandardItemModel()

        # ou = Organisational Units
        try:
            url = 'https://play.dhis2.org/2.28/api/organisationUnits.json?paging=false&level={}'.format(self.level)
            (response, content) = self.nam.request(url)
        except RequestsException as e:
            self.info(e)
            pass

        jsons = content.decode('utf-8')
        jsono = json.loads(jsons)
        for item in jsono['organisationUnits']:
            display_name = item['displayName']
            ou_id = item['id']
            #self.info('{} - {}'.format(ou_id, display_name))
            self.ou_model.appendRow([QStandardItem(display_name), QStandardItem(ou_id)])
        self.dlg.cb_ou.setModel(self.ou_model)

        # dx = indicators and dataelements
        # indicators and dataElements
        try:
            url = 'https://play.dhis2.org/2.28/api/indicators.json?paging=false&level={}'.format(self.level)
            (response, content) = self.nam.request(url)
        except RequestsException as e:
            self.info(e)
            pass

        jsons = content.decode('utf-8')
        jsono = json.loads(jsons)
        for item in jsono['indicators']:
            display_name = item['displayName']
            ou_id = item['id']
            #self.info('{} - {}'.format(ou_id, display_name))
            self.dx_model.appendRow([QStandardItem(display_name), QStandardItem(ou_id)])
        self.dlg.cb_dx.setModel(self.dx_model)

        for pe in ['2017', '2016', '2015', 'LAST_YEAR', 'LAST_5_YEARS']:
            self.pe_model.appendRow([QStandardItem(pe), QStandardItem(pe)])
        self.dlg.cb_pe.setModel(self.pe_model)

        self.ou_items = []
        self.pe_items = []
        self.dx_items = []

        self.dlg.cb_ou.setCurrentIndex(-1)
        self.dlg.cb_dx.setCurrentIndex(-1)
        self.dlg.cb_pe.setCurrentIndex(-1)

        # TODO remember last used index, if available?

        self.gui_inited = True
        self.create_url()
        self.info('Finish INIT dropdowns')

    def cb_ou_changed(self, index):
        self.info('ou index change: {}'.format(index))
        if index < 0:
            return
        ou_id = self.ou_model.index(index, 1).data()
        self.info('ou: {} {} {}'.format(index, ou_id, self.ou_model.index(index, 0).data()))
        if ou_id in self.ou_items:
            self.ou_items.remove(ou_id)
        else:
            self.ou_items.append(ou_id)
        self.create_url()

    def cb_pe_changed(self, index):
        self.info('pe index change: {}'.format(index))
        if index < 0:
            return
        pe_id = self.pe_model.index(index, 1).data()
        self.info('Selected pe: {}'.format(pe_id))  # id
        if pe_id in self.pe_items:
            self.pe_items.remove(pe_id)
        else:
            self.pe_items.append(pe_id)
        self.create_url()

    def cb_dx_changed(self, index):
        self.info('dx index change: {}'.format(index))
        if index < 0:
            return
        dx_id = self.dx_model.index(index, 1).data()
        self.info('Selected dx: {} {} {}'.format(index, dx_id, self.dx_model.index(index, 0).data()))  # displayName
        if dx_id in self.dx_items:
            self.dx_items.remove(dx_id)
        else:
            self.dx_items.append(dx_id)
        self.create_url()

    def cb_level_changed(self, index):
        # redo dropdowns to the Level chossen
        self.gui_inited = False
        self.level = self.dlg.cb_level.currentText()
        self.info('Level change to {}'.format(self.level))
        self.initDropdowns()
        self.create_url()

    def create_url(self):
        self.info('Updating analytics url')
        url = 'https://play.dhis2.org/2.28/api/analytics.json?dimension=dx:{}&dimension=pe:{}&dimension=ou:{}&level={}' \
                .format(';'.join(self.dx_items), ';'.join(self.pe_items), ';'.join(self.ou_items), self.level)
        self.dlg.le_url.setText(url)
        self.analytics_url = url

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&DHIS2 Data Fetcher'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar


    def run(self):
        """

        :return:
        """
        if not self.gui_inited:
            self.initDropdowns()

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
            #pass

            # https://play.dhis2.org/2.28/api/analytics.json?dimension=dx:gNAXtpqAqW2;Lzg9LtG1xg3&dimension=pe:2009;2010;2011;2012;2013;2014;2015;2016;2017;2018&dimension=ou:jUb8gELQApl;fdc6uOvgoji;O6uvpzGd5pu;qhqAxPSTUXp;Vth0fbpFcsO;eIQbndfxQMb;at6UHUQatSo;kJq2mPyFEHo;bL4ooGhyHRQ;jmIPBj66vD6;PMa2VCrupOd;TEQlaapDQoK;lc3eMKXaEfw&displayProperty=NAME&skipMeta=false

            #url = 'https://play.dhis2.org/2.28/api/analytics.json?dimension=dx:gNAXtpqAqW2;Lzg9LtG1xg3&dimension=pe:2009;2010;2011;2012;2013;2014;2015;2016;2017;2018&dimension=ou:jUb8gELQApl;fdc6uOvgoji;O6uvpzGd5pu;qhqAxPSTUXp;Vth0fbpFcsO;eIQbndfxQMb;at6UHUQatSo;kJq2mPyFEHo;bL4ooGhyHRQ;jmIPBj66vD6;PMa2VCrupOd;TEQlaapDQoK;lc3eMKXaEfw&displayProperty=NAME&skipMeta=false'

            #url = 'https://play.dhis2.org/2.28/api/analytics.json?dimension=dx:gNAXtpqAqW2;Lzg9LtG1xg3&dimension=pe:2016Q1:2016Q2:2016Q3:2016Q4:2017Q1:2017Q2:2017Q3:2017Q4:2018Q1:2018Q2&dimension=ou:jUb8gELQApl;fdc6uOvgoji;O6uvpzGd5pu;qhqAxPSTUXp;Vth0fbpFcsO;eIQbndfxQMb;at6UHUQatSo;kJq2mPyFEHo;bL4ooGhyHRQ;jmIPBj66vD6;PMa2VCrupOd;TEQlaapDQoK;lc3eMKXaEfw&displayProperty=NAME&skipMeta=false'

            #url = 'https://play.dhis2.org/2.28/api/analytics.json?dimension=dx:ReUHfIn0pTQ;gNAXtpqAqW2&dimension=pe:2017&dimension=ou:tw532BgmPMY;Eyj2kiEJ7M3'

            # all level 3 ou, birth last 5 years:
            # https://play.dhis2.org/2.28/api/analytics.json?dimension=dx:gNAXtpqAqW2&dimension=pe:LAST_5_YEARS&dimension=ou:O6uvpzGd5pu;fdc6uOvgoji;lc3eMKXaEfw;jUb8gELQApl;PMa2VCrupOd;kJq2mPyFEHo;qhqAxPSTUXp;Vth0fbpFcsO;jmIPBj66vD6;TEQlaapDQoK;bL4ooGhyHRQ;eIQbndfxQMb;at6UHUQatSo

            # ALWAYS grab url from dialog, as it is possible that user copied changed something there
            self.analytics_url = self.dlg.le_url.text()
            url = self.analytics_url

            (response, content) = self.nam.request(url)
            jsons = content.decode('utf-8')
            self.json2features(jsons)


    def json2features(self, jsons):
        jsono = json.loads(jsons)

        print(json.dumps(jsono, sort_keys=True, indent=4))
        #print(jsono['height'])

        from qgis.PyQt.QtCore import QVariant
        from qgis.core import QgsVectorLayer, QgsProject, QgsFields, QgsField, QgsFeature
        # creating memory layer with uri:
        # https://qgis.org/api/qgsmemoryproviderutils_8cpp_source.html
        self.data_layer = QgsVectorLayer('none', 'features', 'memory')

        fields = QgsFields()
        fields.append(QgsField('id', QVariant.String))
        fields.append(QgsField('name', QVariant.String))

        # create as much fields as there are pe_dx combinations
        # eg: 2017_birth, 2016_birth, 2017_measels, 2016_measels
        for pe in jsono['metaData']['dimensions']['pe']:
            for dx in jsono['metaData']['dimensions']['dx']:
                fields.append(QgsField('{}_{}'.format(pe, dx), QVariant.Double))

        #self.info('Fields: {}'.format(fields))

        self.data_layer.dataProvider().addAttributes(fields)
        self.data_layer.updateFields()

        # array with all features
        features = []
        # map which maps the every feature to its OrganisationalUnit
        feature_map = {}
        # create a feature for every ou/OrganisationUnit
        # AND make sure it has the pe_dx combination fields
        for ou in jsono['metaData']['dimensions']['ou']:
            #print(ou)
            f = QgsFeature()
            # set fields
            f.setFields(fields)
            # set id and name of the feature
            f.setAttribute('id', ou)
            f.setAttribute('name', jsono['metaData']['items'][ou]['name'])
            # append feature to features array and feature map
            features.append(f)
            feature_map[ou] = f

        # dynamic?
        # currently the order in which they are in the url is below
        dx_idx = 0
        pe_idx = 1
        ou_idx = 2
        value_idx = 3

        # now every cell in the table has a 'row in the json data', with dx, pe, ou and value
        for row in jsono['rows']:
            # pick feature based on OrganisationalUnit-key from the feature_map
            f = feature_map[row[ou_idx]]
            # attribute key is created from pe_dx string
            attr = '{}_{}'.format(row[pe_idx], row[dx_idx])
            f.setAttribute(attr, row[value_idx])

        self.data_layer.dataProvider().addFeatures(features)

        QgsProject.instance().addMapLayer(self.data_layer)





