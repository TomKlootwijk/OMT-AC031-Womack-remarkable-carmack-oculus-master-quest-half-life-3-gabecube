package org.atomos.radio;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.*;
import android.provider.Settings;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int INK=0xff15312f, MUTED=0xff536966, ACCENT=0xff236a60;
    private TextView status,counts,wifi,cell,sessionInfo;
    private Button start,stop,marker,export;
    private EditText note;
    private Spinner sessionPicker;
    private final ArrayList<File> sessions=new ArrayList<>();
    private final Handler handler=new Handler(Looper.getMainLooper());
    private String exportFileName;
    private boolean exporting;
    private final Runnable refresh=new Runnable(){@Override public void run(){renderState();handler.postDelayed(this,1000);}};
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);
        if(saved!=null)exportFileName=saved.getString("export_file");
        ScrollView scroll=new ScrollView(this); scroll.setFillViewport(true);
        LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(20),dp(20),dp(20),dp(28));scroll.addView(page);
        scroll.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(0,insets.getSystemWindowInsetTop(),0,insets.getSystemWindowInsetBottom());return insets;});
        TextView eyebrow=text("aTOMos  /  RADIO + PACKET STUDIO",12,ACCENT,true);page.addView(eyebrow);
        TextView title=text("Study the signals\naround you.",32,INK,true);margin(page,title,8,14);
        margin(page,text("Wi-Fi access points + cellular measurements\nLocal sessions · timestamped observations",15,MUTED,false),0,18);
        Button packetStudio=button("Packet study · capture / import / decode");margin(page,packetStudio,0,10);packetStudio.setOnClickListener(v->startActivity(new Intent(this,PacketActivity.class)));
        LinearLayout live=card(page);
        status=text("Ready to record",18,INK,true);live.addView(status);
        counts=text("0 Wi-Fi  ·  0 cellular",24,ACCENT,true);margin(live,counts,14,12);
        wifi=text("No Wi-Fi observations yet",14,MUTED,false);margin(live,wifi,0,8);
        cell=text("No cellular observations yet",14,MUTED,false);margin(live,cell,0,12);
        LinearLayout actions=new LinearLayout(this);live.addView(actions);
        start=button("Start session");stop=button("Stop & save");actions.addView(start,new LinearLayout.LayoutParams(0,dp(52),1));actions.addView(stop,new LinearLayout.LayoutParams(0,dp(52),1));
        start.setOnClickListener(v->requestAndStart()); stop.setOnClickListener(v->startService(new Intent(this,RadioService.class).setAction(RadioService.STOP)));
        margin(live,text("Power and quality reports, sampled at the rate Android supplies. Location permission enables radio scans; this app does not collect GPS coordinates.",13,MUTED,false),12,0);
        LinearLayout marks=card(page);marks.addView(text("Mark an experiment",18,INK,true));
        note=new EditText(this);note.setHint("e.g. moved to window · door closed");note.setTextColor(INK);note.setTextSize(15);note.setMaxLines(3);margin(marks,note,8,8);
        marker=button("Add timestamped note");marks.addView(marker);marker.setOnClickListener(v->{String value=note.getText().toString().trim();if(!value.isEmpty()){startService(new Intent(this,RadioService.class).setAction(RadioService.MARK).putExtra("text",value));note.setText("");Toast.makeText(this,"Marker recorded",Toast.LENGTH_SHORT).show();}});
        LinearLayout savedCard=card(page);savedCard.addView(text("Saved sessions",18,INK,true));
        sessionPicker=new Spinner(this);margin(savedCard,sessionPicker,10,8);
        sessionInfo=text("No sessions yet",13,MUTED,false);margin(savedCard,sessionInfo,0,8);
        export=button("Export selected JSONL");savedCard.addView(export);export.setOnClickListener(v->exportSelected());
        Button study=button("Study selected session · signals / identities");savedCard.addView(study);study.setOnClickListener(v->{int i=sessionPicker.getSelectedItemPosition();if(i>=0 && i<sessions.size())startActivity(new Intent(this,StudyActivity.class).putExtra("file",sessions.get(i).getName()));});
        Button currentNetwork=button("Inspect this phone's current IP / DNS / routes");savedCard.addView(currentNetwork);currentNetwork.setOnClickListener(v->{try{ScrollView view=new ScrollView(this);TextView content=text(NetworkSnapshot.read(this).toString(2),13,INK,false);content.setTextIsSelectable(true);content.setPadding(dp(16),dp(12),dp(16),dp(12));view.addView(content);new AlertDialog.Builder(this).setTitle("Current phone network context").setView(view).setPositiveButton("Close",null).show();}catch(Exception e){showError("Network context unavailable",e);}});
        Button reload=button("Refresh session list");savedCard.addView(reload);reload.setOnClickListener(v->loadSessions());
        sessionPicker.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onItemSelected(AdapterView<?> p,View v,int position,long id){renderSession();}public void onNothingSelected(AdapterView<?> p){}});
        LinearLayout setup=card(page);setup.addView(text("Radio setup",18,INK,true));
        margin(setup,text("Keep Wi-Fi and Android Location switched on. Allow precise location. Phone permission adds subscription labels. Screen-off recording uses a visible foreground service and keeps the CPU awake while a session is active.",14,MUTED,false),8,8);
        Button settings=button("Open app permissions & battery settings");setup.addView(settings);settings.setOnClickListener(v->startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:"+getPackageName()))));
        margin(page,text("3.6.1.21 · Tom Klootwijk\nNo account. No automatic upload. Exports contain the observed addresses and identifiers.",12,MUTED,false),18,0);
        setContentView(scroll);loadSessions();renderState();
    }
    private TextView text(String value,int size,int color,boolean bold){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(color);t.setLineSpacing(dp(3),1);if(bold)t.setTypeface(Typeface.DEFAULT,Typeface.BOLD);return t;}
    private Button button(String label){Button b=new Button(this);b.setText(label);b.setAllCaps(false);b.setTextColor(ACCENT);b.setTextSize(14);return b;}
    private void margin(LinearLayout parent,View child,int top,int bottom){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(0,dp(top),0,dp(bottom));parent.addView(child,p);}
    private LinearLayout card(LinearLayout page){LinearLayout c=new LinearLayout(this);c.setOrientation(LinearLayout.VERTICAL);c.setPadding(dp(18),dp(18),dp(18),dp(18));GradientDrawable bg=new GradientDrawable();bg.setColor(Color.WHITE);bg.setCornerRadius(dp(18));c.setBackground(bg);margin(page,c,0,14);return c;}
    private void requestAndStart(){
        ArrayList<String> permissions=new ArrayList<>();
        for(String p:new String[]{Manifest.permission.ACCESS_COARSE_LOCATION,Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.READ_PHONE_STATE})if(checkSelfPermission(p)!=PackageManager.PERMISSION_GRANTED)permissions.add(p);
        if(Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)permissions.add(Manifest.permission.POST_NOTIFICATIONS);
        if(!permissions.isEmpty())requestPermissions(permissions.toArray(new String[0]),1);else begin();
    }
    @Override public void onRequestPermissionsResult(int code,String[] p,int[] results){super.onRequestPermissionsResult(code,p,results);if(code==1)begin();}
    private void begin(){
        if(checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED){new AlertDialog.Builder(this).setTitle("Precise location is needed").setMessage("Android requires precise location permission to report Wi-Fi scans and cell identities. Enable it in app settings, then start a session.").setPositiveButton("Open settings",(d,w)->startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:"+getPackageName())))).setNegativeButton("Close",null).show();return;}
        android.location.LocationManager lm=(android.location.LocationManager)getSystemService(LOCATION_SERVICE);
        if(lm==null || !lm.isLocationEnabled()){new AlertDialog.Builder(this).setTitle("Turn on Android Location").setMessage("Android's radio observation APIs need the system Location switch enabled.").setPositiveButton("Open Location",(d,w)->startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))).setNegativeButton("Close",null).show();return;}
        try{startForegroundService(new Intent(this,RadioService.class).setAction(RadioService.START));}catch(Exception e){showError("Could not start",e);}
    }
    private void renderState(){
        status.setText(RadioService.lastStatus);counts.setText(RadioService.wifiCount+" Wi-Fi  ·  "+RadioService.cellCount+" cellular");
        wifi.setText(RadioService.lastWifi);cell.setText(RadioService.lastCell);start.setEnabled(!RadioService.running);stop.setEnabled(RadioService.running);marker.setEnabled(RadioService.running);export.setEnabled(!RadioService.running && !exporting && !sessions.isEmpty());
        if(!RadioService.running && start.getTag()!=null){start.setTag(null);loadSessions();}
        if(RadioService.running)start.setTag("active");
    }
    private void loadSessions(){
        String selected=sessionPicker.getSelectedItemPosition()>=0 && sessionPicker.getSelectedItemPosition()<sessions.size()?sessions.get(sessionPicker.getSelectedItemPosition()).getName():null;
        File[] found=SessionLog.directory(this).listFiles((dir,name)->name.endsWith(".jsonl"));sessions.clear();if(found!=null){Arrays.sort(found,(a,b)->b.getName().compareTo(a.getName()));Collections.addAll(sessions,found);}
        ArrayList<String> names=new ArrayList<>();int selectedIndex=0;
        for(int i=0;i<sessions.size();i++){File f=sessions.get(i);String name=f.getName();names.add(name.length()>=25?name.substring(0,16)+" · "+name.substring(17,25):name);if(name.equals(selected))selectedIndex=i;}
        ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,names);sessionPicker.setAdapter(adapter);if(!names.isEmpty())sessionPicker.setSelection(selectedIndex);renderSession();
    }
    private void renderSession(){int i=sessionPicker.getSelectedItemPosition();if(i<0 || i>=sessions.size()){sessionInfo.setText("No sessions yet. Start one above.");return;}File f=sessions.get(i);boolean active=f.getName().equals(RadioService.activeFile);sessionInfo.setText((active?"Recording — stop before export":SessionLog.complete(f)?"Closed session":"Interrupted session — missing end record")+"\n"+String.format(Locale.ROOT,"%.1f KB",f.length()/1024.0));}
    private void exportSelected(){
        if(RadioService.running){Toast.makeText(this,"Stop recording before export",Toast.LENGTH_SHORT).show();return;}
        int i=sessionPicker.getSelectedItemPosition();if(i<0 || i>=sessions.size())return;
        File file=sessions.get(i);exportFileName=file.getName();
        Intent create=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/x-ndjson").putExtra(Intent.EXTRA_TITLE,file.getName());
        try{startActivityForResult(create,2);}catch(ActivityNotFoundException e){showError("No document picker available",e);}
    }
    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);
        if(request!=2 || result!=RESULT_OK || data==null || data.getData()==null || exportFileName==null)return;
        final File source=new File(SessionLog.directory(this),exportFileName);final Uri destination=data.getData();
        // Picker can stay open across lifecycle changes. Never copy a currently active log.
        if(source.getName().equals(RadioService.activeFile)){Toast.makeText(this,"Stop recording before export",Toast.LENGTH_LONG).show();return;}
        exporting=true;renderState();
        new Thread(()->{String problem=null;try(InputStream in=new FileInputStream(source);OutputStream out=getContentResolver().openOutputStream(destination,"wt")){if(out==null)throw new IOException("Destination unavailable");byte[] buffer=new byte[65536];int n;while((n=in.read(buffer))!=-1)out.write(buffer,0,n);out.flush();}catch(Exception e){problem=e.toString();}final String error=problem;runOnUiThread(()->{exporting=false;renderState();if(error==null)Toast.makeText(this,"Session exported",Toast.LENGTH_LONG).show();else new AlertDialog.Builder(this).setTitle("Export failed").setMessage(error).setPositiveButton("Close",null).show();});},"atomos-export").start();
    }
    private void showError(String title,Exception e){new AlertDialog.Builder(this).setTitle(title).setMessage(e.getClass().getSimpleName()+": "+e.getMessage()).setPositiveButton("Close",null).show();}
    @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);state.putString("export_file",exportFileName);}
    @Override protected void onResume(){super.onResume();loadSessions();handler.post(refresh);}
    @Override protected void onPause(){handler.removeCallbacks(refresh);super.onPause();}
}
