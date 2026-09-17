package org.atomos.radio;

import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Streaming read-only review: bounded line, entity, detail and plot storage. */
final class SessionReview {
    static final int MAX_ENTITIES=512, MAX_LINE=1024*1024, MAX_POINTS=256;
    final LinkedHashMap<String,Entity> entities=new LinkedHashMap<>();
    final LinkedHashMap<String,Long> counts=new LinkedHashMap<>();
    long rows,badRows,omittedEntities,firstNs=-1,lastNs=-1,unknownTimes,agedRows,recentRows;
    String network="No network-context records in this session",end="No session_end record";
    boolean limited;
    static final class Entity {
        String key,label,kind,lastSource;JSONObject payload;
        long count,repeatedSource,unknownSource,numericCount,recentCount,agedCount;double min=Double.POSITIVE_INFINITY,max=Double.NEGATIVE_INFINITY,last,lastAge=Double.NaN;
        long stride=1;
        final ArrayList<double[]> points=new ArrayList<>();
        void add(long time,double value){numericCount++;min=Math.min(min,value);max=Math.max(max,value);last=value;if(points.size()>=MAX_POINTS){for(int i=points.size()-1;i>=0;i--)if((i&1)==1)points.remove(i);stride*=2;}if(numericCount%stride==0 || points.isEmpty())points.add(new double[]{time,value});}
    }
    static SessionReview read(File file) throws IOException {
        SessionReview review=new SessionReview();
        long snapshotBytes=file.length();
        try(BufferedInputStream in=new BufferedInputStream(new FileInputStream(file))){
            ByteArrayOutputStream line=new ByteArrayOutputStream();long read=0;boolean oversized=false;
            while(read<snapshotBytes){int value=in.read();if(value<0)break;read++;if(value=='\n'){if(oversized)review.badRows++;else review.accept(new String(line.toByteArray(),StandardCharsets.UTF_8));line.reset();oversized=false;}else if(!oversized){if(line.size()>=MAX_LINE){oversized=true;line.reset();}else line.write(value);}if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("Review cancelled");}
            if(line.size()>0 || oversized)review.badRows++; // incomplete append at snapshot boundary
        }
        return review;
    }
    private void accept(String text){
        if(text.trim().isEmpty())return;
        try{
            JSONObject row=new JSONObject(text);String kind=row.getString("kind");JSONObject p=row.getJSONObject("payload");rows++;counts.put(kind,counts.getOrDefault(kind,0L)+1);
            long time;try{time=Long.parseLong(row.getString("received_elapsed_ns"));if(firstNs<0)firstNs=time;lastNs=Math.max(lastNs,time);}catch(Exception e){unknownTimes++;time=-1;}
            if(kind.equals("session_end"))end="Closed session · "+p.optString("reason","unspecified");
            if(kind.equals("status") && p.optString("code").equals("network_context")){network=p.optJSONObject("details")==null?"Unavailable":p.getJSONObject("details").toString(2);return;}
            if(!kind.equals("wifi") && !kind.equals("cell"))return;
            String key=kind.equals("wifi") ? "wifi|"+p.optString("bssid","unknown") : "cell|"+p.optString("rat")+"|"+String.valueOf(p.opt("subscription_id"))+"|"+canonical(p.optJSONObject("identity"));
            Entity entity=entities.get(key);
            if(entity==null){if(entities.size()>=MAX_ENTITIES){omittedEntities++;limited=true;return;}entity=new Entity();entity.key=key;entity.kind=kind;entities.put(key,entity);}
            entity.count++;entity.payload=p.toString().length()<=65536?p:Json.object("display_detail_limit",65536,"message","Latest record exceeds detail-view storage limit; use the original JSONL export","ssid",p.opt("ssid"),"bssid",p.opt("bssid"),"rat",p.opt("rat"),"signal",p.opt("signal"));
            entity.label=kind.equals("wifi") ? p.optString("ssid","Hidden")+" · "+p.optString("bssid") : p.optString("rat")+" · "+canonical(p.optJSONObject("identity"))+" · sub "+String.valueOf(p.opt("subscription_id"));
            String source=row.isNull("source_elapsed_ns")?null:row.optString("source_elapsed_ns",null);
            if(source==null)entity.unknownSource++;else if(source.equals(entity.lastSource))entity.repeatedSource++;entity.lastSource=source;
            double age=Double.NaN;try{if(source!=null && time>=0)age=(time-Long.parseLong(source))/1e9;}catch(NumberFormatException ignored){}
            entity.lastAge=age;boolean recent=Double.isFinite(age) && age>=0 && age<=30;
            if(recent){entity.recentCount++;recentRows++;}else if(Double.isFinite(age) && age>30){entity.agedCount++;agedRows++;}
            Object measurement=kind.equals("wifi")?p.opt("rssi_dbm"):p.optJSONObject("signal")==null?null:p.optJSONObject("signal").opt("dbm");
            if(time>=0 && measurement instanceof Number && recent)entity.add(time-firstNs,((Number)measurement).doubleValue());
        }catch(Exception e){badRows++;}
    }
    private static String canonical(JSONObject object){if(object==null)return"{}";ArrayList<String>keys=new ArrayList<>();object.keys().forEachRemaining(keys::add);Collections.sort(keys);StringBuilder out=new StringBuilder();for(String key:keys)out.append(key).append('=').append(object.opt(key)).append(' ');return out.toString().trim();}
    String summary(){long ap=0,recentAp=0;for(Entity e:entities.values())if(e.kind.equals("wifi")){ap++;if(e.recentCount>0)recentAp++;}return String.format(Locale.ROOT,"%d records · %.1f minutes\nWi-Fi %d · cellular %d · markers %d\n%d of %d AP identities had a report ≤30 s old at receipt\n%d recent radio rows · %d rows older than 30 s\n%s\n%d malformed or unfinished rows · %d missing receipt times",rows,firstNs<0?0:(lastNs-firstNs)/60000000000.0,counts.getOrDefault("wifi",0L),counts.getOrDefault("cell",0L),counts.getOrDefault("marker",0L),recentAp,ap,recentRows,agedRows,end,badRows,unknownTimes)+(limited?"\nEntity display limit reached: "+omittedEntities+" observations omitted from per-entity views":"");}
}
