package org.atomos.radio;

import android.app.*;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.util.*;

public final class StudyActivity extends Activity {
    private LinearLayout page,details;private TextView summary;private Spinner picker;private TrendView plot;private final ArrayList<SessionReview.Entity> items=new ArrayList<>();private Thread worker;
    @Override public void onCreate(Bundle saved){super.onCreate(saved);page=Ui.page(this,"Session study","Review reported signal levels, observed identities and phone network context.");Ui.button(this,page,"Back to recorder",this::finish);summary=Ui.body(this,"Reading session…");Ui.add(Ui.card(this,page),summary,0,0);picker=new Spinner(this);Ui.add(page,picker,0,8);plot=new TrendView(this);page.addView(plot,new LinearLayout.LayoutParams(-1,Ui.dp(this,220)));details=Ui.card(this,page);
        picker.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onItemSelected(AdapterView<?>p,View v,int position,long id){show(position);}public void onNothingSelected(AdapterView<?>p){}});
        String name=getIntent().getStringExtra("file");if(name==null || !new File(name).getName().equals(name)){summary.setText("Choose a saved session in the recorder first.");return;}
        File file=new File(SessionLog.directory(this),name);
        worker=new Thread(()->{try{SessionReview result=SessionReview.read(file);runOnUiThread(()->{if(isFinishing() || isDestroyed())return;summary.setText(result.summary());items.addAll(result.entities.values());items.sort((a,b)->Long.compare(b.count,a.count));ArrayList<String>labels=new ArrayList<>();for(SessionReview.Entity e:items)labels.add(e.label);picker.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels));Ui.button(this,page,"Inspect latest phone network context",()->showText("Phone network context",result.network));});}catch(Exception e){runOnUiThread(()->summary.setText("Could not read session: "+e.getMessage()));}},"atomos-study");worker.start();
    }
    private void show(int position){if(position<0 || position>=items.size())return;SessionReview.Entity e=items.get(position);details.removeAllViews();plot.setPoints(e.points);Ui.add(details,Ui.body(this,e.label),0,10);String range=e.numericCount==0?"No recent numeric values":String.format(Locale.ROOT,"Latest recent %.0f dBm · recent range %.0f to %.0f dBm",e.last,e.min,e.max);Ui.add(details,Ui.body(this,e.count+" observations\n"+e.repeatedSource+" repeated consecutive source timestamps\n"+e.unknownSource+" observations with no source timestamp\n"+e.recentCount+" reports ≤30 s old · "+e.agedCount+" older reports\nLatest source age at receipt: "+(Double.isFinite(e.lastAge)?String.format(Locale.ROOT,"%.2f s",e.lastAge):"unknown")+"\n"+range+"\nReceipt-time plot: "+e.points.size()+" retained recent points; display sampling only."),0,12);Ui.button(this,details,"Inspect latest decoded fields + raw evidence",()->{try{showText("Latest observation",e.payload.toString(2));}catch(Exception ignored){}});}
    private void showText(String title,String text){ScrollView scroll=new ScrollView(this);TextView view=Ui.body(this,text);view.setPadding(Ui.dp(this,16),Ui.dp(this,12),Ui.dp(this,16),Ui.dp(this,12));scroll.addView(view);new AlertDialog.Builder(this).setTitle(title).setView(scroll).setPositiveButton("Close",null).show();}
    @Override protected void onDestroy(){if(worker!=null)worker.interrupt();super.onDestroy();}
}
