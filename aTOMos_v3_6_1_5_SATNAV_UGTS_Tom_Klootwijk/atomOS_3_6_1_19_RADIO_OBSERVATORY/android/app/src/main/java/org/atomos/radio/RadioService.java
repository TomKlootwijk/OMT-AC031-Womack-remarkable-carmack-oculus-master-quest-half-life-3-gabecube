package org.atomos.radio;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.location.LocationManager;
import android.net.wifi.*;
import android.os.*;
import android.telephony.*;
import org.json.*;
import java.io.IOException;
import java.util.*;

public final class RadioService extends Service {
    static final String START="org.atomos.radio.START", STOP="org.atomos.radio.STOP", MARK="org.atomos.radio.MARK";
    static final String CHANNEL="radio_recording";
    static volatile boolean running;
    static volatile String activeFile, sessionId, lastStatus="Ready to record", lastWifi="No observations yet", lastCell="No observations yet";
    static volatile long wifiCount, cellCount, recordCount, startedNs;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private SessionLog log;
    private WifiManager wifi;
    private BroadcastReceiver wifiReceiver;
    private PowerManager.WakeLock wakeLock;
    private long batch;
    private final List<CellSource> sources=new ArrayList<>();
    private static final class CellSource {
        final TelephonyManager manager; final int subId; PhoneStateListener listener; long request=0; boolean pending;
        CellSource(TelephonyManager m,int s) { manager=m; subId=s; }
    }
    @Override public IBinder onBind(Intent i) { return null; }
    @Override public int onStartCommand(Intent intent,int flags,int startId) {
        if(intent==null) { stopSelf(); return START_NOT_STICKY; }
        if(STOP.equals(intent.getAction())) { finish("user_stop"); stopSelf(); }
        else if(MARK.equals(intent.getAction())) {
            String note=intent.getStringExtra("text");
            if(log!=null && note!=null && !note.trim().isEmpty()) append("marker",null,Json.object("text",note.trim()));
            else if(log==null) stopSelf();
        } else if(START.equals(intent.getAction()) && log==null) startRecording();
        return START_NOT_STICKY;
    }
    private boolean granted(String permission) { return checkSelfPermission(permission)==PackageManager.PERMISSION_GRANTED; }
    private JSONObject permissionState() {
        return Json.object("fine_location",granted(Manifest.permission.ACCESS_FINE_LOCATION),"coarse_location",granted(Manifest.permission.ACCESS_COARSE_LOCATION),"phone_state",granted(Manifest.permission.READ_PHONE_STATE),"notifications",Build.VERSION.SDK_INT<33 || granted(Manifest.permission.POST_NOTIFICATIONS));
    }
    private void startRecording() {
        try {
            ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(new NotificationChannel(CHANNEL,"Radio recording",NotificationManager.IMPORTANCE_LOW));
            startForeground(19,notification("Starting Wi-Fi and cellular study"),ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
            log=new SessionLog(this); activeFile=log.file.getName(); sessionId=log.id; running=true;
            wifiCount=0; cellCount=0; recordCount=0; batch=0; startedNs=SystemClock.elapsedRealtimeNanos();
            lastWifi="Waiting for Wi-Fi observations"; lastCell="Waiting for cellular observations";
            append("session",null,Json.object("app","aTOMos Radio","app_version","3.6.1.19","device_manufacturer",Build.MANUFACTURER,"device_model",Build.MODEL,"android_release",Build.VERSION.RELEASE,"android_sdk",Build.VERSION.SDK_INT,
                "signal_type","reported_power_quality","permissions",permissionState(),"wifi_request_interval_ms",35000,"cell_request_interval_ms",10000,
                "clock",Json.object("received_elapsed_ns","monotonic time since boot, includes sleep; decimal string","received_unix_ms","wall clock; may jump, not atomic-clock synchronized","source_elapsed_ns","reported last-seen/modem time since boot; not RF sample time"),
                "metric_units",Json.object("wifi_rssi_dbm","dBm","nr_power","dBm","nr_quality","dB","lte_rssnr_api_unit",Build.VERSION.SDK_INT>=30 ? "dB":"0.1_dB"),
                "raw_waveform_available",false,"complex_csi_available",false));
            if(log==null)return;
            PowerManager pm=(PowerManager)getSystemService(POWER_SERVICE);
            wakeLock=pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"aTOMos:RadioLogging"); wakeLock.setReferenceCounted(false); wakeLock.acquire(60000);
            status("session_started","Recording locally; stop before exporting",Json.object());
            if(log==null)return;
            setupWifi(); setupCellular(); handler.post(cellTick); handler.post(wifiTick);
        } catch(Exception e) { lastStatus="Cannot start: "+e.getClass().getSimpleName()+": "+e.getMessage(); finish("start_failed"); stopSelf(); }
    }
    private Notification notification(String line) {
        PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,RadioService.class).setAction(STOP),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this,CHANNEL).setSmallIcon(android.R.drawable.ic_menu_mylocation).setContentTitle("aTOMos Radio · recording").setContentText(line).setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true).addAction(new Notification.Action.Builder(null,"Stop recording",stop).build()).build();
    }
    private void append(String kind,String source,JSONObject payload) {
        SessionLog target=log; if(target==null)return;
        try { target.append(kind,source,payload); recordCount++; if(kind.equals("wifi"))wifiCount++; if(kind.equals("cell"))cellCount++; }
        catch(IOException e) { lastStatus="Storage error; recording stopped: "+e.getMessage(); finish("storage_error"); stopSelf(); }
    }
    private void status(String code,String message,JSONObject details) { lastStatus=message; append("status",null,Json.object("code",code,"message",message,"details",details)); }
    @SuppressWarnings("deprecation")
    private void setupWifi() {
        wifi=(WifiManager)getApplicationContext().getSystemService(WIFI_SERVICE);
        if(wifi==null) { status("wifi_unavailable","This device exposes no Wi-Fi service",Json.object()); return; }
        final SessionLog owner=log;
        wifiReceiver=new BroadcastReceiver(){ @Override public void onReceive(Context c,Intent i){
            if(log!=owner || !WifiManager.SCAN_RESULTS_AVAILABLE_ACTION.equals(i.getAction()))return;
            captureWifi("broadcast",i.getBooleanExtra(WifiManager.EXTRA_RESULTS_UPDATED,false));
        }};
        IntentFilter filter=new IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION);
        if(Build.VERSION.SDK_INT>=33)registerReceiver(wifiReceiver,filter,Context.RECEIVER_EXPORTED); else registerReceiver(wifiReceiver,filter);
        captureWifi("initial_cache",null);
    }
    @SuppressWarnings("deprecation")
    private void captureWifi(String origin,Boolean updated) {
        try {
            List<ScanResult> results=wifi.getScanResults(); long batchId=++batch;
            status("wifi_results","Wi-Fi: "+results.size()+" AP observations"+(Boolean.FALSE.equals(updated)?" (cached)":""),Json.object("batch_id",batchId,"origin",origin,"results_updated",updated,"count",results.size()));
            for(ScanResult r:results) {
                if(log==null)return;
                String ns=r.timestamp>0 && r.timestamp<Long.MAX_VALUE/1000 ? Long.toString(r.timestamp*1000):null;
                append("wifi",ns,Json.object("ssid",r.SSID,"bssid",r.BSSID,"frequency_mhz",r.frequency,"channel_width",r.channelWidth,"center_frequency0_mhz",r.centerFreq0,"center_frequency1_mhz",r.centerFreq1,
                    "rssi_dbm",r.level,"capabilities",r.capabilities,"batch_id",batchId,"origin",origin,"results_updated",updated,"source_timestamp_unit","us"));
            }
            if(!results.isEmpty()){ ScanResult top=Collections.max(results,Comparator.comparingInt(r->r.level)); lastWifi=(top.SSID==null || top.SSID.isEmpty()?"Hidden SSID":top.SSID)+" · "+top.level+" dBm · "+top.frequency+" MHz"; }
        } catch(SecurityException e) { status("wifi_permission_denied","Wi-Fi permission unavailable",error(e)); }
        catch(Exception e) { status("wifi_read_error","Wi-Fi results unavailable",error(e)); }
    }
    private final Runnable wifiTick=new Runnable(){ @Override public void run(){
        if(log==null)return;
        if(wifi!=null)try {
            boolean accepted=wifi.startScan(); status(accepted?"wifi_scan_requested":"wifi_scan_rejected",accepted?"Wi-Fi scan requested":"Wi-Fi request rejected/throttled",Json.object("accepted",accepted,"wifi_enabled",wifi.isWifiEnabled()));
        } catch(Exception e){status("wifi_scan_error","Wi-Fi scan request failed",error(e));}
        if(log!=null)handler.postDelayed(this,35000);
    }};
    @SuppressWarnings("deprecation")
    private void setupCellular() {
        TelephonyManager base=(TelephonyManager)getSystemService(TELEPHONY_SERVICE);
        if(base==null) { status("cell_unavailable","This device exposes no cellular service",Json.object()); return; }
        if(granted(Manifest.permission.READ_PHONE_STATE)) try {
            SubscriptionManager sm=(SubscriptionManager)getSystemService(TELEPHONY_SUBSCRIPTION_SERVICE);
            List<SubscriptionInfo> subscriptions=sm==null?null:sm.getActiveSubscriptionInfoList();
            if(subscriptions!=null)for(SubscriptionInfo s:subscriptions)sources.add(new CellSource(base.createForSubscriptionId(s.getSubscriptionId()),s.getSubscriptionId()));
        } catch(SecurityException e){status("subscription_permission_denied","Using default cellular source",error(e));}
        catch(Exception e){status("subscription_error","Using default cellular source",error(e));}
        if(sources.isEmpty())sources.add(new CellSource(base,-1));
        final SessionLog owner=log;
        // getAllCellInfo() is device-wide even on createForSubscriptionId managers.
        // Read it once with no subscription attribution; scoped requests/listeners follow.
        try{captureCells(new CellSource(base,-1),base.getAllCellInfo(),"initial_cache");}
        catch(SecurityException e){status("cell_permission_denied","Cell permission unavailable",error(e));}
        catch(Exception e){status("cell_cache_error","Initial cellular cache unavailable",error(e));}
        for(CellSource source:new ArrayList<>(sources)) {
            if(log!=owner)return;
            source.listener=new PhoneStateListener(){ @Override public void onCellInfoChanged(List<CellInfo> list){ if(log==owner)captureCells(source,list,"callback"); }};
            try { source.manager.listen(source.listener,PhoneStateListener.LISTEN_CELL_INFO); }
            catch(Exception e){status("cell_listener_error","Cell callback unavailable; requests remain enabled",error(e));}
        }
    }
    private void captureCells(CellSource source,List<CellInfo> list,String origin) {
        if(log==null)return;
        final SessionLog owner=log;
        if(list==null || list.isEmpty()){status("cell_empty","No cellular observations returned",Json.object("subscription_id",source.subId,"origin",origin)); return;}
        status("cell_results","Cellular: "+list.size()+" observations",Json.object("subscription_id",source.subId,"origin",origin,"count",list.size()));
        for(CellInfo c:list)try {
            if(log!=owner)return;
            JSONObject payload=CellEncoder.encode(c,source.subId,origin); append("cell",CellEncoder.sourceNs(c),payload);
            if(c.isRegistered())lastCell=payload.optString("rat")+" · "+payload.optJSONObject("signal").opt("dbm")+" dBm · serving cell";
        } catch(Exception e){status("cell_decode_error","Could not encode one modem observation",error(e));}
    }
    private final Runnable cellTick=new Runnable(){ @Override public void run(){
        if(log==null)return;
        if(wakeLock!=null)wakeLock.acquire(60000);
        LocationManager lm=(LocationManager)getSystemService(LOCATION_SERVICE);
        status("heartbeat","Recording · Wi-Fi "+wifiCount+" · cellular "+cellCount,Json.object("permissions",permissionState(),"location_enabled",lm!=null && lm.isLocationEnabled(),"elapsed_since_start_ms",(SystemClock.elapsedRealtimeNanos()-startedNs)/1000000));
        final SessionLog owner=log;
        for(CellSource source:new ArrayList<>(sources)) {
            if(log!=owner || log==null)return;
            if(source.pending){status("cell_request_pending","Still waiting for modem response",Json.object("subscription_id",source.subId));continue;}
            final long request=++source.request; source.pending=true;
            handler.postDelayed(()->{if(log==owner && source.pending && source.request==request){source.pending=false; source.request++;status("cell_request_timeout","No modem response within 20 seconds",Json.object("subscription_id",source.subId));}},20000);
            try{source.manager.requestCellInfoUpdate(getMainExecutor(),new TelephonyManager.CellInfoCallback(){
                @Override public void onCellInfo(List<CellInfo> info){if(log!=owner || source.request!=request)return; source.pending=false;captureCells(source,info,"request");}
                @Override public void onError(int code,Throwable detail){if(log!=owner || source.request!=request)return;source.pending=false;status("cell_request_error","Cellular update failed",Json.object("subscription_id",source.subId,"error_code",code,"error",detail==null?null:detail.toString()));}
            });}catch(SecurityException e){source.pending=false;status("cell_permission_denied","Cell permission unavailable",error(e));}
            catch(Exception e){source.pending=false;status("cell_request_error","Cellular update request failed",error(e));}
        }
        if(log!=null)handler.postDelayed(this,10000);
    }};
    private JSONObject error(Exception e){return Json.object("type",e.getClass().getSimpleName(),"message",e.getMessage());}
    @SuppressWarnings("deprecation")
    private void finish(String reason) {
        SessionLog target=log; log=null; running=false;
        handler.removeCallbacksAndMessages(null);
        if(wifiReceiver!=null){try{unregisterReceiver(wifiReceiver);}catch(Exception ignored){}wifiReceiver=null;}
        for(CellSource source:sources)if(source.listener!=null)try{source.manager.listen(source.listener,PhoneStateListener.LISTEN_NONE);}catch(Exception ignored){}
        sources.clear();
        if(wakeLock!=null && wakeLock.isHeld())wakeLock.release(); wakeLock=null;
        boolean closedSuccessfully=true;
        if(target!=null)try{target.close(reason);}catch(IOException e){closedSuccessfully=false;lastStatus="Recording interrupted by storage failure: "+e.getMessage();}
        activeFile=null;
        if(closedSuccessfully && "user_stop".equals(reason))lastStatus="Saved locally. Choose a session to export.";
        stopForeground(STOP_FOREGROUND_REMOVE);
    }
    @Override public void onDestroy(){finish("service_destroyed");super.onDestroy();}
}
