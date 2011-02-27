import gobject
import pygtk
####pygtk.require('2.0')
import gtk
import time, os, re
import threading
from config import config, SuiteConfigError
from port_scan import scan_my_suites
from registration import localdb, centraldb, RegistrationError
from gtkmonitor import monitor
from color_rotator import rotator
from warning_dialog import warning_dialog, info_dialog
from subprocess import call

class chooser_updater(threading.Thread):
    def __init__(self, owner, regd_liststore, db, is_cdb, host, 
            ownerfilt=None, groupfilt=None, namefilt=None ):
        self.ownerfilt = ownerfilt
        self.groupfilt = groupfilt
        self.namefilt = namefilt
        self.db = db
        self.is_cdb = is_cdb
        self.owner = owner
        self.quit = False
        self.host = host
        self.regd_liststore = regd_liststore
        super(chooser_updater, self).__init__()
        self.running_choices = []
        self.line_colors = rotator([ '#ccc', '#aaa' ])
        self.line_colors_cdb = rotator([ '#cfc', '#ada' ])
        self.state_line_colors = rotator([ '#fcc', '#faa' ])

        self.db.load_from_file()
        self.regd_choices = []
        self.regd_choices = self.db.get_list( self.ownerfilt, self.groupfilt, self.namefilt ) 
    
    def run( self ):
        while not self.quit:
            if self.running_choices_changed() or self.regd_choices_changed():
                gobject.idle_add( self.update_liststore )
            time.sleep(1)
        else:
            pass
    
    def running_choices_changed( self ):
        # (name, owner, port)
        suites = scan_my_suites( self.host )
        if suites != self.running_choices:
            self.running_choices = suites
            return True
        else:
            return False

    def regd_choices_changed( self ):
        if not self.db.changed_on_disk():
            return False
        self.db.load_from_file()
        regs = self.db.get_list( self.ownerfilt, self.groupfilt, self.namefilt ) 
        if regs != self.regd_choices:
            self.regd_choices = regs
            return True
        else:
            return False

    def update_liststore( self ):
        # it is expected that a single user will not have a huge number
        # of suites, and registrations will change infrequently,
        # so just clear and recreate the list rather than 
        # adjusting element-by-element.
        ##print "Updating list of available suites"
        ports = {}
        for suite in self.running_choices:
            name, port = suite
            ports[ name ] = port

        self.regd_liststore.clear()
        choices = self.regd_choices
        for reg in choices:
            col = self.line_colors.get_color()
            col_cdb = self.line_colors_cdb.get_color()
            grn = '#2f2'
            #red = '#ff1a45'
            red = self.state_line_colors.get_color()
            name, suite_dir, descr = reg
            suite_dir = re.sub( os.environ['HOME'], '~', suite_dir )
            if self.is_cdb:
                self.regd_liststore.append( [name, col_cdb, '(cdb)', col_cdb, suite_dir, col_cdb, descr, col_cdb ] )
            else:
                if name in ports:
                    self.regd_liststore.append( [name, grn, 'port ' + str(ports[name]), '#19ae0a', suite_dir, grn, descr, grn ] )
                else:
                    self.regd_liststore.append( [name, col, 'dormant', red, suite_dir, col, descr, col ] )

class chooser(object):
    def __init__(self, host, imagedir, readonly=False ):
        self.updater = None
        self.filter_window = None
        self.owner = os.environ['USER']
        self.readonly = readonly

        gobject.threads_init()

        self.host = host
        self.imagedir = imagedir

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        if self.readonly:
            self.window.set_title("_view (READONLY)" )
        else:
            self.window.set_title("_control" )
        self.window.set_size_request(600, 200)
        self.window.set_border_width( 5 )
        self.window.connect("delete_event", self.delete_all_event)

        sw = gtk.ScrolledWindow()
        sw.set_policy( gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC )

        regd_treeview = gtk.TreeView()
        # suite, state, title, colors...
        self.regd_liststore = gtk.ListStore( str, str, str, str, str, str, str, str, )
        regd_treeview.set_model(self.regd_liststore)
        regd_treeview.connect( 'button_press_event', self.on_suite_select )

        self.db_button = gtk.Button( "Central DB" )
        self.db_button.connect("clicked", self.switchdb, None, None )
        self.main_label = gtk.Label( "Local Suite Registration Database" )

        # Start updating the liststore now, as we need values in it
        # immediately below (it may be possible to delay this till the
        # end of __init___() but it doesn't really matter.
        self.cdb = False # start with local reg db
        self.start_updater()

        regd_ts = regd_treeview.get_selection()
        regd_ts.set_mode( gtk.SELECTION_SINGLE )

        cr = gtk.CellRendererText()
        tvc = gtk.TreeViewColumn( 'Suite', cr, text=0, background=1 )
        regd_treeview.append_column( tvc )

        cr = gtk.CellRendererText()
        # use text from col 2, background color stored in col 3:
        tvc = gtk.TreeViewColumn( 'State', cr, text=2, background=3 )
        regd_treeview.append_column( tvc ) 

        cr = gtk.CellRendererText()
        tvc = gtk.TreeViewColumn( 'Title', cr, text=6, background=5 )
        regd_treeview.append_column( tvc )

        cr = gtk.CellRendererText()
        tvc = gtk.TreeViewColumn( 'Definition', cr, text=4, background=7 )
        regd_treeview.append_column( tvc )

        # NOTE THAT WE CANNOT LEAVE ANY SUITE CONTROL WINDOWS OPEN WHEN
        # WE CLOSE THE CHOOSER WINDOW: when launched by the chooser 
        # they are all under the same gtk main loop (?) and do not
        # call gtk_main.quit() unless launched as standalone viewers.
        quit_all_button = gtk.Button( " Quit " )
        quit_all_button.connect("clicked", self.delete_all_event, None, None )

        filter_button = gtk.Button( "Filter" )
        filter_button.connect("clicked", self.filter_popup, None, None )

        vbox = gtk.VBox()
        hbox = gtk.HBox()
        hbox.pack_start( self.main_label )
        vbox.pack_start( hbox, False )

        sw.add( regd_treeview )
        vbox.pack_start( sw, True )

        hbox = gtk.HBox()
        hbox.pack_start( quit_all_button, False )
        hbox.pack_start( self.db_button, False )
        hbox.pack_start( filter_button, False )

        vbox.pack_start( hbox, False )

        self.window.add(vbox)
        self.window.show_all()

        self.viewer_list = []

    def start_updater(self, ownerfilt=None, groupfilt=None, namefilt=None):
        if self.cdb:
            db = centraldb()
            self.db_button.set_label( "Local DB" )
            self.main_label.set_text( "Central Suite Registration Database" )
        else:
            db = localdb()
            self.db_button.set_label( "Central DB" )
            self.main_label.set_text( "Local Suite Registration Database" )
        if self.updater:
            self.updater.quit = True # does this take effect?
        self.updater = chooser_updater( self.owner, self.regd_liststore, 
                db, self.cdb, self.host, ownerfilt, groupfilt, namefilt )
        self.updater.update_liststore()
        self.updater.start()

    def filter(self, w, owner_e, group_e, name_e ):
        ownerfilt = owner_e.get_text()
        groupfilt = group_e.get_text()
        namefilt = name_e.get_text()
        for filt in ownerfilt, groupfilt, namefilt:
            try:
                re.compile( filt )
            except:
                warning_dialog( "Bad Expression: " + filt ).warn()
                self.filter_reset( w, owner_e, group_e, name_e )
                return
        self.start_updater( ownerfilt, groupfilt, namefilt )

    def filter_reset(self, w, owner_e, group_e, name_e ):
        if self.cdb:
            owner_e.set_text('')
        group_e.set_text('')
        name_e.set_text('')
        self.start_updater()

    def filter_popup(self, w, e, data=None):
        self.filter_window = gtk.Window()
        self.filter_window.set_border_width(5)
        self.filter_window.set_title( "DB Filter" )

        vbox = gtk.VBox()

        box = gtk.HBox()
        label = gtk.Label( 'Owner' )
        box.pack_start( label, True )
        owner_entry = gtk.Entry()
        if not self.cdb:
            owner_entry.set_text( self.owner )
            owner_entry.set_sensitive( False )
        box.pack_start (owner_entry, True)
        vbox.pack_start( box )

        box = gtk.HBox()
        label = gtk.Label( 'Group' )
        box.pack_start( label, True )
        group_entry = gtk.Entry()
        box.pack_start (group_entry, True)
        vbox.pack_start( box )

        box = gtk.HBox()
        label = gtk.Label( 'Name' )
        box.pack_start( label, True )
        name_entry = gtk.Entry()
        box.pack_start (name_entry, True)
        vbox.pack_start(box)

        cancel_button = gtk.Button( "Close" )
        cancel_button.connect("clicked", lambda x: self.filter_window.destroy() )

        apply_button = gtk.Button( "Apply" )
        apply_button.connect("clicked", self.filter, owner_entry, group_entry, name_entry )

        reset_button = gtk.Button( "Reset" )
        reset_button.connect("clicked", self.filter_reset, owner_entry, group_entry, name_entry )

        #help_button = gtk.Button( "Help" )
        #help_button.connect("clicked", self.filter_guide )

        hbox = gtk.HBox()
        hbox.pack_start( apply_button, False )
        hbox.pack_start( reset_button, False )
        hbox.pack_start( cancel_button, False )
        #hbox.pack_start( help_button, False )
        vbox.pack_start( hbox )

        self.filter_window.add( vbox )
        self.filter_window.show_all()

    def switchdb( self, w, e, data=None ):
        if self.filter_window:
            self.filter_window.destroy()
        self.cdb = not self.cdb
        self.start_updater()

    def delete_all_event( self, w, e, data=None ):
        self.updater.quit = True
        for item in self.viewer_list:
            item.click_exit( None )
        gtk.main_quit()


    def on_suite_select( self, treeview, event ):
        # the following sets selection to the position at which the
        # right click was done (otherwise selection lags behind the
        # right click):
        x = int( event.x )
        y = int( event.y )
        time = event.time
        pth = treeview.get_path_at_pos(x,y)
        if pth is None:
            return False
        treeview.grab_focus()
        path, col, cellx, celly = pth
        treeview.set_cursor( path, col, 0 )
        selection = treeview.get_selection()
        model, iter = selection.get_selected()
        name = model.get_value( iter, 0 )
        suite_dir = model.get_value( iter, 1 )
        state = model.get_value( iter, 2 ) 

        m = re.match( 'RUNNING \(port (\d+)\)', state )
        port = None
        if m:
            port = m.groups()[0]

        # HERE'S HOW TO DISPLAY MENU ONLY ON RIGHT CLICK
        # (and show task log viewer otherwise):
        #if event.button != 3:
        #    self.show_log( task_id )
        #    return False

        menu = gtk.Menu()

        menu_root = gtk.MenuItem( name )
        menu_root.set_submenu( menu )

        ## make an insensitive item to display selected suite name
        ## so that we can turn the ugly selection off already
        #title_item = gtk.MenuItem( name )
        #menu.append( title_item )
        #title_item.set_sensitive(False)
        #selection.unselect_iter( iter )

        val_item = gtk.MenuItem( 'Validate' )
        menu.append( val_item )
        val_item.connect( 'activate', self.validate_suite, name )

        graph_item = gtk.MenuItem( 'Graph' )
        menu.append( graph_item )
        graph_item.connect( 'activate', self.graph_suite_popup, name )

        edit_item = gtk.MenuItem( 'Edit' )
        menu.append( edit_item )
        edit_item.connect( 'activate', self.edit_suite, name )

        edit_item = gtk.MenuItem( 'Edit Inlined' )
        menu.append( edit_item )
        edit_item.connect( 'activate', self.edit_suite, name, True )

        edit_item = gtk.MenuItem( 'View Inlined' )
        menu.append( edit_item )
        edit_item.connect( 'activate', self.inline_suite_popup, name )

        if self.cdb:
            imp_item = gtk.MenuItem( 'Import' )
            menu.append( imp_item )
            imp_item.connect( 'activate', self.import_suite, name )
        else:
            if state == 'dormant':
                title = 'Start'
            else:
                title = 'Connect'
            title = 'Control'
            con_item = gtk.MenuItem( title )
            menu.append( con_item )
            con_item.connect( 'activate', self.launch_controller, name, port, suite_dir )

            exp_item = gtk.MenuItem( 'Export' )
            menu.append( exp_item )
            exp_item.connect( 'activate', self.export_suite, name )

        menu.show_all()
        menu.popup( None, None, None, event.button, event.time )
        # TO DO: POPUP MENU MUST BE DESTROY()ED AFTER EVERY USE AS
        # POPPING DOWN DOES NOT DO THIS (=> MEMORY LEAK?)
        return True

    def import_suite( self, w, reg ):
        central = centraldb()
        central.load_from_file()
        try:
            dir,descr = central.get( reg )
        except RegistrationError, x:
            warning_dialog( str(x) ).warn()
            return False
        local = localdb() 
        try:
            local.lock()
        except RegistrationError, x:
            warning_dialog( str(x) ).warn()
            return False
        local.load_from_file()
        try:
            local.register( reg, dir, descr )
        except RegistrationError, x:
            warning_dialog( str(x) ).warn()
            return False
        local.unlock()
        local.dump_to_file()

    def export_suite( self, w, reg ):
        local = localdb()
        local.load_from_file()
        try:
            dir,descr = local.get( reg )
        except RegistrationError, x:
            warning_dialog( str(x) ).warn()
            return False
        central = centraldb() 
        try:
            central.lock()
        except RegistrationError, x:
            warning_dialog( str(x) ).warn()
            return False
        central.load_from_file()
        try:
            central.register( reg, dir, descr )
        except RegistrationError, x:
            warning_dialog( str(x) ).warn()
            return False
        central.unlock()
        central.dump_to_file()

    def graph_suite_popup( self, w, reg ):
        try:
            from graphing import xdot
        except:
            warning_dialog( "Graphing is not available;\nplease install graphviz\nand pygraphviz.").warn()
            return False

        window = gtk.Window()
        window.set_border_width(5)
        window.set_title( "Suite Graph Options for '" + reg + "'")

        vbox = gtk.VBox()
        box = gtk.HBox()

        # TO DO: NOT RADIO BUTTONS (multiple choices should be allowed)
        warm_cb = gtk.CheckButton( "Warm Start" )
        runtime_cb = gtk.CheckButton( "Runtime Graph" )
        
        outputfile_entry = gtk.Entry()
        if not self.cdb:
            outputfile_entry.set_sensitive( False )
        box.pack_start (outputfile_entry, True)
 
        box.pack_start (warm_cb, True)
        vbox.pack_start( box )

        cancel_button = gtk.Button( "Close" )
        cancel_button.connect("clicked", lambda x: window.destroy() )
        ok_button = gtk.Button( "View" )
        ok_button.connect("clicked", self.inline_suite, reg,
                mark_cb, label_cb, nojoin_cb, single_cb  )

        #help_button = gtk.Button( "Help" )
        #help_button.connect("clicked", self.stop_guide )

        hbox = gtk.HBox()
        hbox.pack_start( cancel_button, False )
        hbox.pack_start( ok_button, False )
        #hbox.pack_start( help_button, False )
        vbox.pack_start( hbox )

        window.add( vbox )
        window.show_all()


        # fake a full cycle time
        hour = '00'
        stop = '06'
        raw = False
        #ctime = '29990101' + hour
        #window = MyDotWindow( reg, ctime, stop, raw, None )
        #window.parse_graph()
        #?window.show_all()

        # TO DO 1/ use non-shell non-blocking launch here?
        # TO DO 2/ instead of external process make part of chooser app?
        # Would have to launch in own thread as xdot is interactive?
        # Probably not necessary ... same goes for controller actually?
        if self.cdb:
            call( 'capture "_graph -c ' + reg + ' ' + hour + ' ' + stop + '" &', shell=True )
        else:
            call( 'capture "_graph ' + reg + ' ' + hour + ' ' + stop + '" &', shell=True )

    def inline_suite_popup( self, w, reg ):
        window = gtk.Window()
        window.set_border_width(5)
        window.set_title( "Inline Viewing Options for '" + reg + "'")

        vbox = gtk.VBox()
        box = gtk.HBox()

        mark_cb = gtk.CheckButton( "Marked" )
        label_cb = gtk.CheckButton( "Labeled" )
        nojoin_cb = gtk.CheckButton( "Unjoined" )
        single_cb = gtk.CheckButton( "Singled" )
        
        box.pack_start (mark_cb, True)
        box.pack_start (label_cb, True)
        box.pack_start (nojoin_cb, True)
        box.pack_start (single_cb, True)
        vbox.pack_start( box )

        cancel_button = gtk.Button( "Close" )
        cancel_button.connect("clicked", lambda x: window.destroy() )
        ok_button = gtk.Button( "View" )
        ok_button.connect("clicked", self.inline_suite, reg,
                mark_cb, label_cb, nojoin_cb, single_cb  )

        #help_button = gtk.Button( "Help" )
        #help_button.connect("clicked", self.stop_guide )

        hbox = gtk.HBox()
        hbox.pack_start( cancel_button, False )
        hbox.pack_start( ok_button, False )
        #hbox.pack_start( help_button, False )
        vbox.pack_start( hbox )

        window.add( vbox )
        window.show_all()

    def edit_suite( self, w, reg, inlined=False ):
        if inlined:
            extra = '-i '
        else:
            extra = ''
        if self.cdb:
            extra += '-c '
        call( 'capture "_edit ' + extra + ' ' + reg + '" &', shell=True  )
        return False

    def inline_suite( self, w, reg, markcb, lblcb, nojcb, sngcb ):
        extra = ''
        if self.cdb:
            extra += '-c '
        if markcb.get_active():
            extra += ' -m'
        if nojcb.get_active():
            extra += ' -n'
        if lblcb.get_active():
            extra += ' -l'
        if sngcb.get_active():
            extra += ' -s'
        call( 'capture "_inline ' + extra + ' ' + reg + '" &', shell=True  )
        return False

    def validate_suite( self, w, name ):
        # the following requires gui capture of stdout and stderr somehow:
        #try:
        #    conf = config( name )
        #    conf.load_tasks()
        #except SuiteConfigError,x:
        #    warning_dialog( str(x) ).warn()
        #    return False
        #except:
        #    raise
        #else:
        #    info_dialog( "Suite " + name + " validates OK." ).inform()

        # for now, launch external process:
        call( 'capture "_validate ' + name  + '" &', shell=True )

    def launch_controller( self, w, name, port, suite_dir ):
        # get suite logging directory
        # logging_dir = os.path.join( config(name)['top level logging directory'], name ) 
        # TO LAUNCH A CONTROL GUI AS PART OF THIS APP:
        #tv = monitor(name, self.owner, self.host, port, suite_dir,
        #    logging_dir, self.imagedir, self.readonly )
        #self.viewer_list.append( tv )
        #return False
        call( 'capture "gcylc ' + name  + '" &', shell=True )


