package org.atomos.radio;

import android.content.Context;
import android.os.SystemClock;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.*;

/** Append-only UTF-8 evidence. A missing session_end is an interrupted session, never repaired silently. */
final class SessionLog {
    final String id = UUID.randomUUID().toString();
    final File file;
    private final FileOutputStream stream;
    private final BufferedWriter writer;
    private long seq;
    private boolean closed;
    private final Map<String, Long> counts = new LinkedHashMap<>();
    SessionLog(Context context) throws IOException {
        File dir = directory(context);
        if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("Cannot create session directory");
        SimpleDateFormat fmt = new SimpleDateFormat("yyyyMMdd'T'HHmmss'Z'", Locale.ROOT);
        fmt.setTimeZone(TimeZone.getTimeZone("UTC"));
        file = new File(dir, fmt.format(new Date()) + "_" + id + ".jsonl");
        stream = new FileOutputStream(file);
        writer = new BufferedWriter(new OutputStreamWriter(stream, StandardCharsets.UTF_8));
    }
    static File directory(Context c) { return new File(c.getFilesDir(), "sessions"); }
    synchronized void append(String kind, String sourceNs, JSONObject payload) throws IOException {
        if (closed) throw new IOException("Session is closed");
        JSONObject row = Json.object("schema", "atomos.radio.v1", "session_id", id, "seq", seq,
            "kind", kind, "received_elapsed_ns", Long.toString(SystemClock.elapsedRealtimeNanos()),
            "received_unix_ms", System.currentTimeMillis(), "source_elapsed_ns", sourceNs, "payload", payload);
        writer.write(row.toString()); writer.newLine(); writer.flush();
        counts.put(kind, counts.getOrDefault(kind, 0L) + 1); seq++;
    }
    synchronized JSONObject counts() { return new JSONObject(counts); }
    synchronized long count(String kind) { return counts.getOrDefault(kind, 0L); }
    synchronized void close(String reason) throws IOException {
        if (closed) return;
        try { append("session_end", null, Json.object("reason", reason, "counts_before_end", counts())); stream.getFD().sync(); }
        finally { closed=true; writer.close(); }
    }
    static boolean complete(File file) {
        // Session terminator is small. Read only the tail, not a potentially day-long capture.
        try (RandomAccessFile in = new RandomAccessFile(file, "r")) {
            long length=in.length(); int amount=(int)Math.min(16384, length);
            byte[] tail=new byte[amount]; in.seek(length-amount); in.readFully(tail);
            String[] lines=new String(tail, StandardCharsets.UTF_8).trim().split("\\n");
            return new JSONObject(lines[lines.length-1]).optString("kind").equals("session_end");
        } catch (Exception e) { return false; }
    }
}
