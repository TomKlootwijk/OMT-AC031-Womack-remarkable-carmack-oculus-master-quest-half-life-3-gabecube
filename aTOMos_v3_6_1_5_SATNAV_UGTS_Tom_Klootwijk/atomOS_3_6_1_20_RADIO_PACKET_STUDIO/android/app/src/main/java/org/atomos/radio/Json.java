package org.atomos.radio;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.util.Collection;

final class Json {
    private Json() {}
    static JSONObject object(Object... pairs) {
        JSONObject out = new JSONObject();
        try {
            for (int i=0; i<pairs.length; i+=2) out.put((String)pairs[i], pairs[i+1] == null ? JSONObject.NULL : pairs[i+1]);
        } catch (JSONException e) { throw new IllegalArgumentException(e); }
        return out;
    }
    static Object metric(int value) { return value == Integer.MAX_VALUE || value == Integer.MIN_VALUE ? JSONObject.NULL : value; }
    static Object identity(int value) { return value < 0 || value == Integer.MAX_VALUE ? JSONObject.NULL : value; }
    static Object identity(long value) { return value < 0 || value == Long.MAX_VALUE ? JSONObject.NULL : value; }
    static Object text(CharSequence value) { return value == null ? JSONObject.NULL : value.toString(); }
}
