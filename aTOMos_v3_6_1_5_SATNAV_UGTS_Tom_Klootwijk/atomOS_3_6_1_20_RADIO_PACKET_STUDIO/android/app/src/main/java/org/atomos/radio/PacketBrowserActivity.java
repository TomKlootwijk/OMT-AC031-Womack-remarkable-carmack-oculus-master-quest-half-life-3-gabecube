package org.atomos.radio;

import android.app.*;
import android.os.Bundle;
import android.text.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;

public final class PacketBrowserActivity extends Activity {
    private final ArrayList<JSONObject> packets=new ArrayList<>(),visible=new ArrayList<>();
    private Spinner filter;private EditText search;private TextView status;private ArrayAdapter<String> adapter;private long total;
    @Override public void onCreate(Bundle saved){super.onCreate(saved);LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);int padding=Ui.dp(this,18);page.setPadding(padding,padding,padding,padding);page.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(padding,padding+insets.getSystemWindowInsetTop(),padding,padding+insets.getSystemWindowInsetBottom());return insets;});setContentView(page);
        Ui.add(page,Ui.text(this,"Packet browser",26,Ui.INK,true),0,6);Ui.button(this,page,"Back to capture study",this::finish);
        filter=new Spinner(this);filter.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"All","UDP","DNS","TCP","TLS"}));Ui.add(page,filter,2,2);
        search=new EditText(this);search.setTextSize(15);search.setSingleLine(true);search.setHint("Filter address, port, protocol or DNS name");Ui.add(page,search,2,6);
        status=Ui.text(this,"Loading retained packet details…",12,Ui.MUTED,false);Ui.add(page,status,2,10);
        ListView list=new ListView(this);adapter=new ArrayAdapter<String>(this,android.R.layout.simple_list_item_1,new ArrayList<>()){@Override public View getView(int position,View convert,android.view.ViewGroup parent){TextView view=(TextView)super.getView(position,convert,parent);view.setTextSize(14);view.setTextColor(Ui.INK);view.setPadding(padding,Ui.dp(PacketBrowserActivity.this,14),padding,Ui.dp(PacketBrowserActivity.this,14));return view;}};list.setAdapter(adapter);page.addView(list,new LinearLayout.LayoutParams(-1,0,1));list.setOnItemClickListener((parent,view,position,id)->inspect(visible.get(position)));
        filter.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onItemSelected(AdapterView<?>p,View v,int i,long id){refresh();}public void onNothingSelected(AdapterView<?>p){}});search.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){refresh();}public void afterTextChanged(Editable e){}});
        String name=getIntent().getStringExtra("report");if(name==null || !new File(name).getName().equals(name)){status.setText("Choose a capture first.");return;}File file=new File(new File(getFilesDir(),"packet_captures"),name);
        new Thread(()->{try{if(file.length()>8L*1024*1024)throw new IOException("Report exceeds the 8 MiB browser limit");JSONObject report=new JSONObject(new String(Files.readAllBytes(file.toPath()),StandardCharsets.UTF_8));JSONArray rows=report.optJSONArray("packets");ArrayList<JSONObject> loaded=new ArrayList<>();if(rows!=null)for(int i=0;i<Math.min(200,rows.length());i++)if(rows.optJSONObject(i)!=null)loaded.add(rows.optJSONObject(i));runOnUiThread(()->{if(isDestroyed())return;total=report.optLong("packets_seen");packets.addAll(loaded);filter.setSelection(1);refresh();});}catch(Exception e){runOnUiThread(()->{if(!isDestroyed())status.setText("Could not load packet details: "+e.getMessage());});}},"atomos-packet-browser").start();
    }
    private void refresh(){if(adapter==null)return;String selected=filter.getSelectedItem()==null?"All":filter.getSelectedItem().toString();visible.clear();adapter.clear();for(JSONObject packet:packets)if(PacketPresentation.matches(packet,selected,search.getText().toString())){visible.add(packet);adapter.add(PacketPresentation.row(packet));}status.setText(visible.size()+" matches in "+packets.size()+" retained packet details; "+total+" packets scanned.\nOnly the first 200 packet details are retained. Export the original capture for full analysis.");adapter.notifyDataSetChanged();}
    private void inspect(JSONObject packet){ScrollView scroll=new ScrollView(this);TextView body=Ui.body(this,PacketPresentation.detail(packet));body.setPadding(Ui.dp(this,16),Ui.dp(this,12),Ui.dp(this,16),Ui.dp(this,12));scroll.addView(body);new AlertDialog.Builder(this).setTitle("Packet #"+packet.optInt("index")).setView(scroll).setPositiveButton("Close",null).setNeutralButton("Payload hex",(d,w)->plain("Payload hex",PacketPresentation.hex(packet))).setNegativeButton("Raw fields",(d,w)->{try{plain("Raw decoded fields",packet.toString(2));}catch(Exception ignored){}}).show();}
    private void plain(String title,String content){ScrollView scroll=new ScrollView(this);TextView body=Ui.body(this,content);body.setPadding(Ui.dp(this,16),Ui.dp(this,12),Ui.dp(this,16),Ui.dp(this,12));scroll.addView(body);new AlertDialog.Builder(this).setTitle(title).setView(scroll).setPositiveButton("Close",null).show();}
}
