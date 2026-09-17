package org.atomos.radio;

import android.test.InstrumentationTestCase;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

public final class ReviewTest extends InstrumentationTestCase {
    public void testOldCacheIsSeparatedFromRecentReports() throws Exception {
        File file=File.createTempFile("review", ".jsonl",getInstrumentation().getTargetContext().getCacheDir());
        try {
            StringBuilder text=new StringBuilder();long now=20000000000000L;
            text.append(row("session",now,null,Json.object()));
            text.append(row("wifi",now,now-18000000000000L,Json.object("ssid","old AP","bssid","02:00:00:00:00:01","rssi_dbm",-30)));
            text.append(row("wifi",now+1000000000L,now,Json.object("ssid","fresh AP","bssid","02:00:00:00:00:02","rssi_dbm",-60)));
            text.append(row("wifi",now+2000000000L,now,Json.object("ssid","fresh AP","bssid","02:00:00:00:00:02","rssi_dbm",-60)));
            text.append(row("session_end",now+3000000000L,null,Json.object("reason","test")));
            Files.write(file.toPath(),text.toString().getBytes(StandardCharsets.UTF_8));SessionReview review=SessionReview.read(file);
            assertEquals(5,review.rows);assertEquals(1,review.agedRows);assertEquals(2,review.recentRows);assertEquals(2,review.entities.size());assertTrue(review.summary().contains("1 of 2 AP identities"));
            SessionReview.Entity old=review.entities.get("wifi|02:00:00:00:00:01");assertTrue(old.points.isEmpty());assertEquals(18000.0,old.lastAge,0.01);
            SessionReview.Entity fresh=review.entities.get("wifi|02:00:00:00:00:02");assertEquals(1,fresh.repeatedSource);assertEquals(-60.0,fresh.min,0.01);assertEquals(2,fresh.points.size());
        }finally{file.delete();}
    }
    public void testPartialLineAndNullSignalAreNotInvented() throws Exception {
        File file=File.createTempFile("review", ".jsonl",getInstrumentation().getTargetContext().getCacheDir());
        try{Files.write(file.toPath(),(row("cell",2000000000L,null,Json.object("rat","LTE","identity",Json.object("ci",42),"signal",Json.object("dbm",null)))+"{broken").getBytes(StandardCharsets.UTF_8));SessionReview review=SessionReview.read(file);assertEquals(1,review.rows);assertEquals(1,review.badRows);assertTrue(review.entities.values().iterator().next().points.isEmpty());assertEquals(1,review.entities.values().iterator().next().unknownSource);}finally{file.delete();}
    }
    private String row(String kind,long time,Long source,JSONObject payload){return Json.object("kind",kind,"received_elapsed_ns",Long.toString(time),"source_elapsed_ns",source==null?null:Long.toString(source),"payload",payload).toString()+"\n";}
}
