import java.io.*;
import java.util.*;
import app.freerouting.Freerouting;
import app.freerouting.settings.*;
import app.freerouting.core.*;
import app.freerouting.interactive.*;
import app.freerouting.board.*;
import app.freerouting.autoroute.*;
import app.freerouting.datastructures.*;
public class LocalRoute {
 public static void main(String[] a)throws Exception {
  Freerouting.globalSettings=new GlobalSettings();Freerouting.globalSettings.usageAndDiagnosticData.disableAnalytics=true;
  RoutingJob job=new RoutingJob();job.setDummyInputFile(a[0]);
  HeadlessBoardManager mgr=new HeadlessBoardManager(Locale.ENGLISH,job);
  IdentificationNumberGenerator ids=new ItemIdentificationNumberGenerator();
  System.out.println(mgr.loadFromSpecctraDsn(new FileInputStream(a[0]),new BoardObserverAdaptor(),ids));
  RouterSettings settings=mgr.get_settings().autoroute_settings;settings.maxPasses=6;settings.set_stop_pass_no(6);settings.maxThreads=1;
  StoppableThread thread=new StoppableThread(){protected void thread_action(){}};
  BatchAutorouter router=new BatchAutorouter(thread,mgr.get_routing_board(),settings,false,true,100,500);
  router.addTaskStateChangedEventListener(e->{System.out.println("PASS "+e.getPassNumber()+" "+e.getTaskState());try{mgr.saveAsSpecctraSessionSes(new FileOutputStream(a[1]),a[0]);}catch(Exception x){throw new RuntimeException(x);}});
  router.runBatchLoop();mgr.saveAsSpecctraSessionSes(new FileOutputStream(a[1]),a[0]);System.out.println("FINISHED");System.exit(0);
 }
}
