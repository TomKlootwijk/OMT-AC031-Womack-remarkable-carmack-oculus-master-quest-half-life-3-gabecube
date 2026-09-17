package org.atomos.radio;

import android.app.*;
import android.os.*;
import android.text.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;

/** Streams the imported raw capture for each bounded, globally filtered page. */
public final class PacketBrowserActivity extends Activity {
    private static final int PAGE_SIZE=200;
    private static final String[] FILTERS={"All","UDP","DNS","TCP","TLS"};
    private final ArrayList<JSONObject> visible=new ArrayList<>();
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final PageRequestGate requests=new PageRequestGate();
    private Future<?> pending;
    private Runnable debounce;
    private Spinner filter;private EditText search;private TextView status;private ArrayAdapter<String> adapter;
    private Button previous,next,reload;private ListView list;
    private File capture;private String expectedSha="";private int offset;private boolean ready;

    @Override public void onCreate(Bundle saved){super.onCreate(saved);
        LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);int padding=Ui.dp(this,18);page.setPadding(padding,padding,padding,padding);
        page.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(padding,padding+insets.getSystemWindowInsetTop(),padding,padding+insets.getSystemWindowInsetBottom());return insets;});setContentView(page);
        boolean landscape=getResources().getConfiguration().orientation==android.content.res.Configuration.ORIENTATION_LANDSCAPE;
        if(landscape){LinearLayout heading=new LinearLayout(this);heading.setGravity(Gravity.CENTER_VERTICAL);heading.addView(Ui.text(this,"Packet browser",22,Ui.INK,true),new LinearLayout.LayoutParams(0,-2,1));Button back=new Button(this);back.setText("Back to capture study");back.setAllCaps(false);back.setOnClickListener(v->finish());heading.addView(back);Ui.add(page,heading,0,2);}
        else{Ui.add(page,Ui.text(this,"Packet browser",26,Ui.INK,true),0,6);Ui.button(this,page,"Back to capture study",this::finish);}
        filter=new Spinner(this);filter.setContentDescription("Packet protocol filter");filter.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,FILTERS));
        search=new EditText(this);search.setTextSize(15);search.setSingleLine(true);search.setFilters(new InputFilter[]{new InputFilter.LengthFilter(256)});search.setHint("Search all decoded metadata / UDP previews");search.setContentDescription("Search capture");
        if(landscape){LinearLayout controls=new LinearLayout(this);controls.addView(filter,new LinearLayout.LayoutParams(Ui.dp(this,110),-2));controls.addView(search,new LinearLayout.LayoutParams(0,-2,1));Ui.add(page,controls,2,4);}
        else{Ui.add(page,filter,2,2);Ui.add(page,search,2,6);}
        status=Ui.text(this,"Select an imported capture to browse.",12,Ui.MUTED,false);Ui.add(page,status,2,6);
        LinearLayout navigation=new LinearLayout(this);navigation.setOrientation(LinearLayout.HORIZONTAL);Ui.add(page,navigation,0,4);
        previous=navigationButton(navigation,"Previous",()->loadPage(Math.max(0,offset-PAGE_SIZE),false));
        next=navigationButton(navigation,"Next",()->loadPage(offset+PAGE_SIZE,false));
        previous.setEnabled(false);next.setEnabled(false);
        reload=Ui.button(this,page,"Reload changed capture",()->{expectedSha="";loadPage(0,false);});reload.setVisibility(View.GONE);
        list=new ListView(this);adapter=new ArrayAdapter<String>(this,android.R.layout.simple_list_item_1,new ArrayList<>()){@Override public View getView(int position,View convert,ViewGroup parent){TextView view=(TextView)super.getView(position,convert,parent);view.setTextSize(14);view.setTextColor(Ui.INK);view.setPadding(padding,Ui.dp(PacketBrowserActivity.this,14),padding,Ui.dp(PacketBrowserActivity.this,14));return view;}};
        list.setAdapter(adapter);page.addView(list,new LinearLayout.LayoutParams(-1,0,1));list.setOnItemClickListener((parent,view,position,id)->{if(position>=0&&position<visible.size())inspect(visible.get(position));});
        String name=saved==null?getIntent().getStringExtra("capture"):saved.getString("capture");
        expectedSha=saved==null?getIntent().getStringExtra("expected_sha"):saved.getString("expected_sha");if(expectedSha==null)expectedSha="";
        if(name==null || !new File(name).getName().equals(name) || !(name.endsWith(".pcap")||name.endsWith(".pcapng"))){status.setText("Choose an imported capture first.");return;}
        capture=new File(new File(getFilesDir(),"packet_captures"),name);
        offset=saved==null?0:Math.max(0,saved.getInt("offset"));int selected=saved==null?1:saved.getInt("filter",1);filter.setSelection(Math.max(0,Math.min(FILTERS.length-1,selected)));
        if(saved!=null)search.setText(saved.getString("query",""));
        filter.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){private int last=filter.getSelectedItemPosition();public void onItemSelected(AdapterView<?>p,View v,int i,long id){if(last!=i){last=i;if(ready)loadPage(0,false);}}public void onNothingSelected(AdapterView<?>p){}});
        search.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){if(ready)loadPage(0,true);}public void afterTextChanged(Editable e){}});
        ready=true;loadPage(offset,false);
    }
    private Button navigationButton(LinearLayout row,String title,Runnable action){Button b=new Button(this);b.setText(title);b.setAllCaps(false);b.setTextColor(Ui.ACCENT);b.setOnClickListener(v->action.run());row.addView(b,new LinearLayout.LayoutParams(0,-2,1));return b;}
    private void loadPage(int requestedOffset,boolean delayed){
        if(capture==null || isFinishing() || isDestroyed())return;
        long generation=requests.begin();if(pending!=null)pending.cancel(true);if(debounce!=null)handler.removeCallbacks(debounce);
        offset=requestedOffset;previous.setEnabled(false);next.setEnabled(false);reload.setVisibility(View.GONE);visible.clear();adapter.clear();
        String protocol=String.valueOf(filter.getSelectedItem()),query=search.getText().toString().trim(),pin=expectedSha;
        status.setText("Scanning original capture for "+protocol+" matches…\nUp to 100,000 packets / 64 MiB; at most 200 displayed per page.");
        debounce=()->{if(!requests.accepts(generation))return;pending=worker.submit(()->{try{JSONObject report=new JSONObject(PacketDecoder.decodePage(capture,protocol,query,requestedOffset,PAGE_SIZE,pin));handler.post(()->{if(!requests.accepts(generation)||isFinishing()||isDestroyed())return;showPage(report);});}catch(Exception e){handler.post(()->{if(!requests.accepts(generation)||isFinishing()||isDestroyed())return;status.setText("Could not inspect capture: "+e.getMessage());});}});};
        handler.postDelayed(debounce,delayed?300:0);
    }
    private void showPage(JSONObject report){
        if("source_changed".equals(report.optString("status"))){status.setText("The capture bytes changed. This page was discarded to avoid mixing different files. Reload to bind a new SHA-256 and restart from the first page.");reload.setVisibility(View.VISIBLE);return;}
        if(expectedSha.isEmpty())expectedSha=report.optString("file_sha256","");
        JSONObject paging=report.optJSONObject("page");if(paging==null){status.setText("Decoder returned no page metadata.");return;}
        JSONArray rows=report.optJSONArray("packets");if(rows!=null)for(int i=0;i<Math.min(PAGE_SIZE,rows.length());i++){JSONObject packet=rows.optJSONObject(i);if(packet!=null){visible.add(packet);adapter.add(PacketPresentation.row(packet));}}
        adapter.notifyDataSetChanged();list.setSelection(0);int count=visible.size();long matches=paging.optLong("total_matches");
        String range=count==0?"No matches on this page":("Matches "+(offset+1)+"–"+(offset+count)+" of "+matches);
        String scope=report.optBoolean("complete")?"Capture scan finished":"Only the inspected prefix is counted; "+report.optString("status")+". The unscanned tail may contain more matches";
        status.setText(range+" · "+report.optLong("packets_seen")+" packets inspected\n"+scope+". Filter/search covers every inspected packet's decoded metadata and bounded previews. Page limit: 200.\nUnsupported "+report.optInt("unsupported_packets")+" · malformed "+report.optInt("malformed_packets")+" · truncated "+report.optInt("capture_truncated_packets"));
        previous.setEnabled(offset>0);next.setEnabled(paging.optBoolean("has_next"));
    }
    @Override protected void onSaveInstanceState(Bundle saved){super.onSaveInstanceState(saved);if(capture!=null)saved.putString("capture",capture.getName());saved.putString("expected_sha",expectedSha);saved.putInt("offset",offset);saved.putInt("filter",filter.getSelectedItemPosition());saved.putString("query",search.getText().toString());}
    @Override protected void onDestroy(){requests.close();if(pending!=null)pending.cancel(true);handler.removeCallbacksAndMessages(null);worker.shutdownNow();super.onDestroy();}
    private void inspect(JSONObject packet){ScrollView scroll=new ScrollView(this);TextView body=Ui.body(this,PacketPresentation.detail(packet));body.setPadding(Ui.dp(this,16),Ui.dp(this,12),Ui.dp(this,16),Ui.dp(this,12));scroll.addView(body);new AlertDialog.Builder(this).setTitle("Packet #"+packet.optInt("index")).setView(scroll).setPositiveButton("Close",null).setNeutralButton("Payload hex",(d,w)->plain("Payload hex",PacketPresentation.hex(packet))).setNegativeButton("Raw fields",(d,w)->{try{plain("Raw decoded fields",packet.toString(2));}catch(Exception ignored){}}).show();}
    private void plain(String title,String content){ScrollView scroll=new ScrollView(this);TextView body=Ui.body(this,content);body.setPadding(Ui.dp(this,16),Ui.dp(this,12),Ui.dp(this,16),Ui.dp(this,12));scroll.addView(body);new AlertDialog.Builder(this).setTitle(title).setView(scroll).setPositiveButton("Close",null).show();}
}
