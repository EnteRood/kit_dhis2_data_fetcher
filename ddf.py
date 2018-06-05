# -*- coding: utf-8 -*-
"""
/***************************************************************************
 DHIS2DataFetcher
                                 A QGIS plugin
 Fetch Data from DHIS2
                              -------------------
        begin                : 2018-02-14
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
from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QVariant, QUrl
from qgis.PyQt.QtGui import QIcon, QStandardItemModel, QStandardItem, QDesktopServices
from qgis.PyQt.QtWidgets import QAction, QMenu, QDialog, QDialogButtonBox, QSizePolicy, QVBoxLayout

from qgis.core import QgsMessageLog, Qgis, QgsApplication, QgsVectorLayer, QgsProject, QgsFields, QgsField, QgsFeature
from qgis.gui import QgsAuthConfigSelect

import os.path
import json

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .ddf_dialog import DHIS2DataFetcherDialog
from .networkaccessmanager import NetworkAccessManager, RequestsException


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
        self.dlg = DHIS2DataFetcherDialog(self.iface.mainWindow())

        self.dlg.cb_ou.currentIndexChanged.connect(self.cb_ou_changed)
        self.dlg.cb_pe.currentIndexChanged.connect(self.cb_pe_changed)
        self.dlg.cb_dx.currentIndexChanged.connect(self.cb_dx_changed)
        self.dlg.cb_level.currentIndexChanged.connect(self.cb_level_changed)

        self.dlg.btn_load_geodata.clicked.connect(self.load_geodata_in_layer)
        self.dlg.btn_new_dataset.clicked.connect(self.new_dataset)
        self.dlg.btn_api_config.clicked.connect(self.selectAuthConfig)

        self.auth_dlg = None

        # Declare instance attributes
        self.actions = []
        #self.menu = self.tr(u'KIT - DHIS2 Data Fetcher')
        self.menu = QMenu(self.tr(u'KIT - DHIS2 Data Fetcher'))
        self.iface.pluginMenu().addMenu(self.menu)
        self.menu.setIcon(QIcon(':/plugins/DHIS2DataFetcher/icon_kit.png'))

        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'DHIS2DataFetcher')
        self.toolbar.setObjectName(u'DHIS2DataFetcher')

        self.MSG_TITLE = "DHIS2 datafetcher"

        self.api_url = 'https://play.dhis2.org/2.29/api/'
        self.api_url = None  # url as defined by user in authoristation profile
        self.auth_id = None  # authorisation id to be used in nam creation AND vectorlayer creation uri

        self.gui_inited = False
        self.nam = None  # created in gui during authorisation profile choice

        self.ou_items = []
        self.pe_items = []
        self.dx_items = []

        # TODO: coming from GUI
        # for now use playground
        self.username = 'admin'
        self.password = 'district'

        self.analytics_url = ''
        self.level = 2

        # connect to the iface.projectRead signal to be able to refresh data in a project with a dhis2 layer
        self.iface.projectRead.connect(self.update_dhis2_project)


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
            # self.iface.addPluginToMenu(
            #     self.menu,
            #     action)
            self.menu.addAction(action)

        self.actions.append(action)

        return action

    def info(self, msg=""):
        QgsMessageLog.logMessage('{}'.format(msg), self.MSG_TITLE, Qgis.Info)

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/DHIS2DataFetcher/icon_kit.png'
        self.add_action(
            icon_path,
            text=self.tr(u'KIT - Fetch DHIS2 Data'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # help menu
        icon_path = ':/plugins/DHIS2DataFetcher/icon_kit.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Code and (preliminary) Documentation'),
            callback=self.show_help,
            add_to_toolbar=False,
            parent=self.iface.mainWindow())

    def show_help(self):
        #docs = os.path.join(os.path.dirname(__file__), "help/html", "index.html")
        #QDesktopServices.openUrl(QUrl("file:" + docs))
        QDesktopServices.openUrl(QUrl("https://github.com/rduivenvoorde/kit_dhis2_data_fetcher/"))

    # def initAuthentication(self):
    #
    #     # https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/authentication.html#term-authentication-config
    #     authMgr = QgsAuthManager.instance()
    #     if authMgr.masterPasswordIsSet():
    #         msg = 'Authentication master password not recognized'
    #         assert authMgr.masterPasswordSame("your master password"), msg
    #     else:
    #         msg = 'Master password could not be set'
    #         # The verify parameter check if the hash of the password was
    #         # already saved in the authentication db
    #         assert authMgr.setMasterPassword("your master password", verify=True), msg

    def initDropdowns(self):

        #self.info('INIT dropdowns')

        # we have to fill drop downs
        # ??? without authentication ???
        # TODO authentications admin/district
        # https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/authentication.html#term-authentication-config
        # TODO: To let a user create a basic authentication via this dialog
        # QgsAuthConfigSelect().show()
        # TODO: zelf een authconfig aanmaken hier op basis van ???
        # TODO: ALS gebruiker dit heeft gedaan, dan achterhalen wat the authid is van zijn/haar config

        # ou = Organisational Units
        self.ou_model = QStandardItemModel()
        self.pe_model = QStandardItemModel()
        self.dx_model = QStandardItemModel()

        # ou = Organisational Units
        try:
            url = '{}organisationUnits.json?paging=false&level={}'.format(self.api_url, self.level)
            (response, content) = self.nam.request(url)
        except RequestsException as e:
            self.info(e)
            #pass

        jsons = content.decode('utf-8')
        jsono = json.loads(jsons)
        # easy way to add ALL organisationUnits
        self.ou_model.appendRow([QStandardItem("ALL"), QStandardItem("ALL")])
        for item in jsono['organisationUnits']:
            display_name = item['displayName']
            ou_id = item['id']
            #self.info('{} - {}'.format(ou_id, display_name))
            self.ou_model.appendRow([QStandardItem(display_name), QStandardItem(ou_id)])
        self.dlg.cb_ou.setModel(self.ou_model)

        # dx = indicators and data elements
        # indicators
        try:
            # indicators
            url = '{}indicators.json?paging=false&level={}'.format(self.api_url, self.level)
            (response, content) = self.nam.request(url)
        except RequestsException as e:
            self.info(e)
            pass
        jsono = json.loads(content.decode('utf-8'))
        for item in jsono['indicators']:
            display_name = item['displayName']
            ou_id = item['id']
            #self.info('{} - {}'.format(ou_id, display_name))
            self.dx_model.appendRow([QStandardItem(display_name), QStandardItem(ou_id)])

        # dataElements
        try:
            # dataelements
            url = '{}dataElements.json?paging=false&level={}'.format(self.api_url, self.level)
            (response, content) = self.nam.request(url)
        except RequestsException as e:
            self.info(e)
            pass
        jsono = json.loads(content.decode('utf-8'))
        for item in jsono['dataElements']:
            display_name = item['displayName']
            ou_id = item['id']
            #self.info('{} - {}'.format(ou_id, display_name))
            self.dx_model.appendRow([QStandardItem(display_name), QStandardItem(ou_id)])

        self.dlg.cb_dx.setModel(self.dx_model)

        for pe in ['2018', '2017', '2016', '2015', 'LAST_YEAR', 'LAST_5_YEARS',
                   'THIS_MONTH', 'LAST_MONTH', 'LAST_3_MONTHS', 'MONTHS_THIS_YEAR', 'LAST_12_MONTHS']:
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
        #self.info('Finish INIT dropdowns')


    def load_geodata_in_layer(self):
        self.info('Loading level {} geodata'.format(self.level))

        # try:
        #     url = 'https://play.dhis2.org/2.28/api/organisationUnits.geojson?paging=false&level={}'.format(self.level)
        #     (response, content) = self.nam.request(url)
        # except RequestsException as e:
        #     self.info(e)
        #     pass
        # import tempfile
        # from datetime import datetime
        # file_name = tempfile.gettempdir() + os.sep + 'dhis2geodata_' + datetime.now().strftime("%Y%m%d%H%M%S") + '.geojson'
        # with open(file_name, 'wb') as f:
        #     f.write(content)
        # geojson_layer = QgsVectorLayer(file_name, 'Level {} organisationUnits'.format(self.level), 'ogr')

        url = "{}organisationUnits.geojson?paging=false&level={} authcfg='{}'".format(self.api_url, self.level, self.auth_id)
        geojson_layer = QgsVectorLayer(url, 'Level {} organisationUnits'.format(self.level), 'ogr')
        if geojson_layer.isValid():
            QgsProject.instance().addMapLayer(geojson_layer)
        else:
            self.info('Problem loading: {}'.format(url))

    def new_dataset(self):
        #self.info('Clean dataset url')
        # by setting another level, the url is cleaned
        self.cb_level_changed(0)

    def cb_ou_changed(self, index):
        #self.info('ou index change: {}'.format(index))
        if index < 0:
            return
        ou_id = self.ou_model.index(index, 1).data()
        self.info('ou: {} {} {}'.format(index, ou_id, self.ou_model.index(index, 0).data()))
        if ou_id == 'ALL':
            # start with a clean sheet first:
            self.ou_items = []
            for idx in range(0, self.ou_model.rowCount()-1):
                self.ou_items.append(self.ou_model.index(idx, 1).data())
        elif ou_id in self.ou_items:
            self.ou_items.remove(ou_id)
        else:
            self.ou_items.append(ou_id)
        self.create_url()

    def cb_pe_changed(self, index):
        #self.info('pe index change: {}'.format(index))
        if index < 0:
            return
        pe_id = self.pe_model.index(index, 1).data()
        #self.info('Selected pe: {}'.format(pe_id))  # id
        if pe_id in self.pe_items:
            self.pe_items.remove(pe_id)
        else:
            self.pe_items.append(pe_id)
        self.create_url()

    def cb_dx_changed(self, index):
        #self.info('dx index change: {}'.format(index))
        if index < 0:
            return
        dx_id = self.dx_model.index(index, 1).data()
        #self.info('Selected dx: {} {} {}'.format(index, dx_id, self.dx_model.index(index, 0).data()))  # displayName
        if dx_id in self.dx_items:
            self.dx_items.remove(dx_id)
        else:
            self.dx_items.append(dx_id)
        self.create_url()

    def cb_level_changed(self, index):
        # redo dropdowns to the Level chossen
        self.gui_inited = False
        self.level = self.dlg.cb_level.currentText()
        #self.info('Level change to {}'.format(self.level))
        self.initDropdowns()
        self.create_url()

    def create_url(self):
        #self.info('Updating analytics url')
        url = '{}analytics.json?dimension=dx:{}&dimension=pe:{}&dimension=ou:{}&level={}'\
            .format(self.api_url, ';'.join(self.dx_items), ';'.join(self.pe_items), ';'.join(self.ou_items), self.level)
        self.dlg.le_url.setText(url)
        self.analytics_url = url

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'KIT - DHIS2 Data Fetcher'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar
        self.iface.projectRead.disconnect(self.update_dhis2_project)

    def run(self):
        """

        :return:
        """
        if self.api_url is None:
            if not self.selectAuthConfig():
                # returns False on failure
                # TODO message?
                return

        # still None ?
        if self.api_url is None:
            msg = self.tr("Please create or select an Authorisation Profile first (see help). Not able to run without api url")
            self.iface.messageBar().pushCritical(self.MSG_TITLE, msg)
            self.info(msg)
            return

        if not self.gui_inited:
            self.initDropdowns()

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # ALWAYS grab url from dialog, as it is possible that user copied changed something there
            self.analytics_url = self.dlg.le_url.text()
            url = self.analytics_url
            self.json2features(url)

    def update_dhis2_project(self):
        # now go over layers and check if they have a dhis2_url property
        p = QgsProject.instance()
        for lname in p.mapLayers():
            lyr = p.mapLayer(lname)
            url = lyr.customProperty('dhis2_url', '')
            # TODO also authid to use!! Either saved or find it in profiles
            if len(url) > 0:
                #self.info('OK url !!')
                self.info(url)
                # if so: fetch fresh data, but reuse layer
                self.json2features(url, lyr)

    def json2features(self, url, data_layer=None):
        try:
            (response, content) = self.nam.request(url, method="GET")
        except RequestsException as e:
            self.info('ERROR: {}'.format(e))
            return

        jsons = content.decode('utf-8')

        jsono = json.loads(jsons)

        #print(json.dumps(jsono, sort_keys=True, indent=4))
        #print(jsono['height'])

        # creating memory layer with uri:
        # https://qgis.org/api/qgsmemoryproviderutils_8cpp_source.html
        if data_layer is None:
            data_layer = QgsVectorLayer('none', 'DHIS2 data', 'memory')

        fields = QgsFields()
        fields.append(QgsField('id', QVariant.String))
        fields.append(QgsField('name', QVariant.String))

        metadata_items = jsono['metaData']['items']

        # create as much fields as there are pe_dx combinations
        # eg: 2017_birth, 2016_birth, 2017_measels, 2016_measels
        for pe in jsono['metaData']['dimensions']['pe']:
            for dx in jsono['metaData']['dimensions']['dx']:
                #field_alias = '{} {} ({})'.format(pe, metadata_items[dx]['name'], dx)
                field_alias = '{} {}'.format(pe, metadata_items[dx]['name'])
                field = QgsField('{}_{}'.format(pe, dx), QVariant.Double, comment=field_alias)
                field.setAlias(field_alias)
                fields.append(field)

        #self.info('Fields: {}'.format(fields))

        # clean up first
        data_layer.dataProvider().deleteAttributes(data_layer.dataProvider().attributeIndexes())
        data_layer.updateFields()

        # set new attributes
        data_layer.dataProvider().addAttributes(fields)
        data_layer.updateFields()

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
            # Births attended by skilled health personnel (estimated pregancies)
            f.setAttribute(attr, row[value_idx])

        data_layer.dataProvider().addFeatures(features)

        # add it to the project
        QgsProject.instance().addMapLayer(data_layer)
        # 'save' the data url of the layer into the project properties
        # https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/settings.html
        data_layer.setCustomProperty("dhis2_url", url)


    def selectAuthConfig(self):
        # to be able to run while authmanager was crashing...
        # self.api_url = 'https://play.dhis2.org/2.29/api/'
        # self.auth_id = 'dhis2ap'
        # return True
        if self.auth_dlg is None:
            self.auth_dlg = AuthConfigSelectDialog(self.iface.mainWindow())
        self.auth_dlg.show()
        result = self.auth_dlg.exec_()
        if result:
            conf_id = self.auth_dlg.select.configId()
            self.api_url = None
            if len(conf_id) > 0:
                auth_man = QgsApplication.authManager()
                uri = auth_man.availableAuthMethodConfigs()[conf_id].uri()
                if uri.startswith('http'):
                    # make sure it ends with /
                    if not uri.endswith('/'):
                        uri = uri + '/'
                    self.api_url = uri
                    self.auth_id = conf_id
                    # Set authid to use to 'dhis2ap' which has api url: https://play.dhis2.org/2.29/api/
                    self.info("Set authid to use to '{}' which has api url: {}".format(self.auth_id, self.api_url))

                    # note: user has to create an authenticaton configuration with id 'self.auth_id' to authorize the HTTP requests
                    self.nam = NetworkAccessManager(authid=self.auth_id, exception_class=RequestsException, debug=False)
                    self.initDropdowns()
                    return True
        self.info("Problem setting authid or url??? DHIS2 Api not reachable!")

        return False

class AuthConfigSelectDialog(QDialog):
    def __init__(self, parent):
        QDialog.__init__(self, parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        #self.setLayout(QGridLayout())
        self.setLayout(QVBoxLayout())
        #self.layout().setContentsMargins(0, 0, 0, 0)
        self.select = QgsAuthConfigSelect()
        #self.layout().addWidget(self.select, 0, 0, 2, Qt.AlignLeft)
        self.layout().addWidget(self.select)
        self.buttonbox = QDialogButtonBox(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        #self.layout().addWidget(self.buttonbox, 1, 0, 2, Qt.AlignRight)
        self.layout().addWidget(self.buttonbox)
        self.buttonbox.accepted.connect(self.accept)
        self.buttonbox.rejected.connect(self.reject)









