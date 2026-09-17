package org.atomos.radio;

import android.test.InstrumentationTestCase;
import org.json.JSONObject;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Runs against Android's real JSON implementation, not framework stub methods. */
public final class ContractTest extends InstrumentationTestCase {
    public void testUnavailableAndValidIdentityBoundaries() {
        assertSame(JSONObject.NULL,Json.identity(Integer.MAX_VALUE));
        assertSame(JSONObject.NULL,Json.identity(Long.MAX_VALUE));
        assertSame(JSONObject.NULL,Json.identity(-1));
        assertEquals(2147483647L,Json.identity(2147483647L)); // valid NR NCI
        assertEquals(68719476735L,Json.identity(68719476735L));
        assertEquals(0,Json.metric(0));
        assertSame(JSONObject.NULL,Json.metric(Integer.MAX_VALUE));
    }
    public void testModemTimestampUnitsAndUnknownSentinel() {
        assertEquals("123456789",CellEncoder.sourceNs(123456789L,0,29));
        assertEquals("123000000",CellEncoder.sourceNs(123456789L,123,30));
        assertNull(CellEncoder.sourceNs(Long.MAX_VALUE,Long.MAX_VALUE/1000000,36));
        assertNull(CellEncoder.sourceNs(0,0,36));
        assertNull(CellEncoder.sourceNs(-1,-1,29));
    }
    public void testConcurrentAppendSequenceAndClosedSession() throws Exception {
        SessionLog log=new SessionLog(getInstrumentation().getTargetContext());
        try {
            log.append("session",null,Json.object("fixture",true));
            List<Throwable> errors=Collections.synchronizedList(new ArrayList<>());
            Thread[] threads=new Thread[4];
            for(int i=0;i<threads.length;i++){threads[i]=new Thread(()->{try{for(int j=0;j<25;j++)log.append("marker",null,Json.object("text","φ · LTE · "+j));}catch(Throwable e){errors.add(e);}});threads[i].start();}
            for(Thread thread:threads)thread.join();
            assertTrue(errors.toString(),errors.isEmpty());
            assertFalse(SessionLog.complete(log.file));log.close("test_complete");assertTrue(SessionLog.complete(log.file));
            List<String> lines=Files.readAllLines(log.file.toPath(),StandardCharsets.UTF_8);assertEquals(102,lines.size());
            long prior=-1;
            for(int i=0;i<lines.size();i++){JSONObject row=new JSONObject(lines.get(i));assertEquals(i,row.getInt("seq"));assertEquals(log.id,row.getString("session_id"));assertEquals("atomos.radio.v1",row.getString("schema"));assertTrue(row.isNull("source_elapsed_ns"));long now=Long.parseLong(row.getString("received_elapsed_ns"));assertTrue(now>=prior);prior=now;}
            assertEquals("φ · LTE · 0",new JSONObject(lines.get(1)).getJSONObject("payload").getString("text"));
            try{log.append("marker",null,Json.object("text","late"));fail("Closed log accepted a write");}catch(java.io.IOException expected){}
        } finally {log.close("test_cleanup");Files.deleteIfExists(log.file.toPath());}
    }
}
