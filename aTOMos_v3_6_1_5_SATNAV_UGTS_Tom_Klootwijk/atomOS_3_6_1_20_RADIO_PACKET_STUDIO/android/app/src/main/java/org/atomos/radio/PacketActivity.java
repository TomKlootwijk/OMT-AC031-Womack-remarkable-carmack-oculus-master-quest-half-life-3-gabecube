package org.atomos.radio;

import android.app.*;
import android.content.*;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.database.Cursor;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;

/** Local capture import/review. Capturing itself is explicitly delegated to the PCAPdroid app. */
public final class PacketActivity extends Activity {
    private static final int IMPORT=10,EXPORT=11;
    private static final long MAX_IMPORT=64L*1024*1024;
    private LinearLayout page,reportCard;
    private TextView progress;
    private Spinner picker;
    private final ArrayList<File> captures=new ArrayList<>();
    private String pendingExport;
    private boolean busy;
    private JSONObject selectedReport;
    private String currentReportName;
    private TextView backgroundState;
    private final android.os.Handler statusHandler=new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable refreshBackground=new Runnable(){@Override public void run(){if(backgroundState!=null)backgroundState.setText(RadioService.running?"Radio logger: recording · Wi-Fi "+RadioService.wifiCount+" · cellular "+RadioService.cellCount+". PCAPdroid shows its own packet-capture status.":"Radio logger: stopped. PCAPdroid shows its own packet-capture status.");statusHandler.postDelayed(this,2000);}};
    @Override public void onCreate(Bundle state){super.onCreate(state);if(state!=null)pendingExport=state.getString("pending_export");
        page=Ui.page(this,"Packet study","Capture this phone's traffic in PCAPdroid, then inspect the exported packet file locally.");Ui.button(this,page,"Back to recorder",this::finish);
        LinearLayout capture=Ui.card(this,page);Ui.add(capture,Ui.text(this,"1. Capture on this phone",18,Ui.INK,true),0,8);
        Ui.add(capture,Ui.body(this,"Start a radio session in the recorder for ambient Wi-Fi and cellular logging. It continues in the background with an ongoing notification. For this phone's packets, open PCAPdroid, select PCAP output, start capture and accept Android's VPN prompt. Its separate foreground capture continues while you use other apps or return here. Stop each recorder from its own controls."),0,8);
        backgroundState=Ui.body(this,"");Ui.add(capture,backgroundState,0,8);
        Ui.button(this,capture,"Capture phone packets · open PCAPdroid",this::launchCapture);
        LinearLayout files=Ui.card(this,page);Ui.add(files,Ui.text(this,"2. Import and decode",18,Ui.INK,true),0,8);
        Ui.button(this,files,"Import capture · Downloads or USB storage",()->{if(busy)return;Intent select=new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");try{startActivityForResult(select,IMPORT);}catch(ActivityNotFoundException e){problem(e.toString());}});
        progress=Ui.body(this,"Files stay in this app until you export them. Import limit: 64 MiB per file.");Ui.add(files,progress,6,8);picker=new Spinner(this);Ui.add(files,picker,0,8);Ui.button(this,files,"Review selected capture",this::reviewSelected);Ui.button(this,files,"Refresh imported files",this::loadFiles);
        Ui.button(this,files,"Export decoded report JSON",()->chooseExport(true));Ui.button(this,files,"Export original capture bytes",()->chooseExport(false));
        reportCard=Ui.card(this,page);Ui.add(reportCard,Ui.body(this,"No capture selected. Encrypted payloads remain encrypted; decoded protocol metadata is labelled separately from guesses."),0,0);
        Ui.add(files,Ui.body(this,"For USB OTG storage: connect and mount the drive, open Import, then select the drive in Android's document-picker menu. This imports capture files; it does not turn a USB radio adapter into a live sniffer."),6,4);loadFiles();
    }
    private File directory(){File dir=new File(getFilesDir(),"packet_captures");if(!dir.isDirectory())dir.mkdirs();return dir;}
    private void launchCapture(){Intent launch=getPackageManager().getLaunchIntentForPackage("com.emanuelef.remote_capture");if(launch==null){new AlertDialog.Builder(this).setTitle("PCAPdroid is not installed").setMessage("Install PCAPdroid from its official store listing, then return here. Capturing starts only when you start it in PCAPdroid.").setPositiveButton("Open official listing",(d,w)->startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse("https://play.google.com/store/apps/details?id=com.emanuelef.remote_capture")))).setNegativeButton("Close",null).show();}else startActivity(launch);}
    private void loadFiles(){String prior=selected()==null?null:selected().getName();captures.clear();File[] files=directory().listFiles((d,n)->n.endsWith(".pcap") || n.endsWith(".pcapng"));if(files!=null){Arrays.sort(files,(a,b)->b.getName().compareTo(a.getName()));Collections.addAll(captures,files);}ArrayList<String>names=new ArrayList<>();int selection=0;for(int i=0;i<captures.size();i++){File f=captures.get(i);names.add(f.getName()+String.format(Locale.ROOT," · %.1f KiB",f.length()/1024.0));if(f.getName().equals(prior))selection=i;}picker.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,names));if(!names.isEmpty())picker.setSelection(selection);}
    private File selected(){int i=picker==null?-1:picker.getSelectedItemPosition();return i<0 || i>=captures.size()?null:captures.get(i);}
    private String displayName(Uri uri){try(Cursor c=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME},null,null,null)){if(c!=null && c.moveToFirst())return c.getString(0);}catch(Exception ignored){}return "capture";}
    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(result!=RESULT_OK || data==null || data.getData()==null)return;if(request==IMPORT)importCapture(data.getData());else if(request==EXPORT && pendingExport!=null)exportTo(data.getData());}
    private void importCapture(Uri uri){if(busy)return;busy=true;progress.setText("Importing capture…");String original=displayName(uri);String ext=original!=null && original.toLowerCase(Locale.ROOT).endsWith(".pcapng")?".pcapng":".pcap";File output=new File(directory(),System.currentTimeMillis()+"_"+UUID.randomUUID().toString().substring(0,8)+ext);File partial=new File(directory(),output.getName()+".partial");
        new Thread(()->{try{long bytes=0;try(InputStream in=getContentResolver().openInputStream(uri);OutputStream out=new FileOutputStream(partial)){if(in==null)throw new IOException("Source unavailable");byte[] buffer=new byte[65536];int n;while((n=in.read(buffer))!=-1){bytes+=n;if(bytes>MAX_IMPORT)throw new IOException("Capture exceeds the 64 MiB import limit. Split or export a shorter capture.");out.write(buffer,0,n);}}if(!partial.renameTo(output))throw new IOException("Cannot finalize imported file");JSONObject report=new JSONObject(PacketDecoder.decode(output));report.put("import_original_name",original==null?JSONObject.NULL:original);Files.write(new File(output.getPath()+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));runOnUiThread(()->{if(isDestroyed())return;busy=false;loadFiles();picker.setSelection(captures.indexOf(output));progress.setText("Imported original bytes and decoded report saved locally.");currentReportName=output.getName()+".json";showReport(report);});}catch(Exception e){partial.delete();runOnUiThread(()->{if(isDestroyed())return;busy=false;loadFiles();problem("Import/decode failed: "+e.getMessage()+". A completed raw import, if present, remains available.");});}},"atomos-pcap-import").start();
    }
    private void reviewSelected(){File capture=selected();if(capture==null || busy)return;busy=true;progress.setText("Reading capture…");new Thread(()->{try{File reportFile=new File(capture.getPath()+".json");JSONObject prior=reportFile.exists() && reportFile.length()<4L*1024*1024?new JSONObject(new String(Files.readAllBytes(reportFile.toPath()),StandardCharsets.UTF_8)):null;JSONObject report=new JSONObject(PacketDecoder.decode(capture));if(prior!=null && prior.has("import_original_name"))report.put("import_original_name",prior.opt("import_original_name"));Files.write(reportFile.toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));JSONObject ready=report;runOnUiThread(()->{if(isDestroyed())return;busy=false;progress.setText("Review refreshed with the current decoder. Raw capture unchanged.");currentReportName=reportFile.getName();showReport(ready);});}catch(Exception e){runOnUiThread(()->{if(isDestroyed())return;busy=false;problem(e.toString());});}},"atomos-pcap-review").start();}
    private void showReport(JSONObject report){selectedReport=report;reportCard.removeAllViews();Ui.add(reportCard,Ui.text(this,"Decoded capture",20,Ui.INK,true),0,10);Ui.add(reportCard,Ui.body(this,report.optString("format","Unknown format")+" · "+report.optString("status")+"\n"+report.optLong("packets_seen")+" packets visited\n"+report.optLong("file_bytes")+" bytes\nContainer scan finished: "+report.optBoolean("complete")+"\nUnsupported "+report.optInt("unsupported_packets")+" · malformed "+report.optInt("malformed_packets")+" · truncated "+report.optInt("capture_truncated_packets")),0,12);Ui.button(this,reportCard,"Browse packets · readable UDP / DNS",()->{if(currentReportName!=null)startActivity(new Intent(this,PacketBrowserActivity.class).putExtra("report",currentReportName));});Ui.add(reportCard,Ui.body(this,"Protocols\n"+pretty(report.opt("protocol_counts"))),0,12);Ui.button(this,reportCard,"Inspect endpoints / addresses",()->inspect("Endpoints",report.opt("endpoints")));Ui.button(this,reportCard,"Inspect packet summaries / DNS",()->inspect("Packet summaries",report.opt("packets")));Ui.button(this,reportCard,"Inspect limits and decoding issues",()->inspect("Decode boundaries",Json.object("issues",report.opt("issues"),"limits",report.opt("limits"))));Ui.button(this,reportCard,"Inspect full report JSON",()->inspect("Report",report));}
    private String pretty(Object value){try{return value instanceof JSONObject?((JSONObject)value).toString(2):value instanceof JSONArray?((JSONArray)value).toString(2):String.valueOf(value);}catch(Exception e){return String.valueOf(value);}}
    private void inspect(String title,Object data){String content=pretty(data);if(content.length()>250000)content=content.substring(0,250000)+"\n[Display limit reached; export JSON for full report]";ScrollView scroll=new ScrollView(this);TextView text=Ui.body(this,content);text.setPadding(Ui.dp(this,16),Ui.dp(this,12),Ui.dp(this,16),Ui.dp(this,12));scroll.addView(text);new AlertDialog.Builder(this).setTitle(title).setView(scroll).setPositiveButton("Close",null).show();}
    private void chooseExport(boolean report){File capture=selected();if(capture==null || busy)return;File source=report?new File(capture.getPath()+".json"):capture;if(!source.isFile()){problem("Review this capture first to create its decoded report.");return;}pendingExport=source.getName();Intent create=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType(report?"application/json":"application/octet-stream").putExtra(Intent.EXTRA_TITLE,source.getName());try{startActivityForResult(create,EXPORT);}catch(ActivityNotFoundException e){problem(e.toString());}}
    private void exportTo(Uri destination){File source=new File(directory(),pendingExport);if(!source.getName().equals(pendingExport)){problem("Invalid export path");return;}busy=true;progress.setText("Exporting…");new Thread(()->{try(InputStream in=new FileInputStream(source);OutputStream out=getContentResolver().openOutputStream(destination,"wt")){if(out==null)throw new IOException("Destination unavailable");byte[] buffer=new byte[65536];int n;while((n=in.read(buffer))!=-1)out.write(buffer,0,n);out.flush();runOnUiThread(()->{if(isDestroyed())return;busy=false;progress.setText("Export complete.");});}catch(Exception e){runOnUiThread(()->{if(isDestroyed())return;busy=false;problem(e.toString());});}},"atomos-pcap-export").start();}
    @Override protected void onResume(){super.onResume();statusHandler.post(refreshBackground);}
    @Override protected void onPause(){statusHandler.removeCallbacks(refreshBackground);super.onPause();}
    private void problem(String message){progress.setText(message);}
    @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);state.putString("pending_export",pendingExport);}
}
