package org.atomos.radio;

import android.test.InstrumentationTestCase;
import org.json.*;

public final class PacketPresentationTest extends InstrumentationTestCase {
    public void testDnsIsIncludedInUdpFilterAndReadable() throws Exception {
        JSONObject p=Json.object("index",7,"protocol","DNS","protocols",new JSONArray().put("IPv6").put("UDP").put("DNS"),"source_ip","2001:db8::1","source_port",53000,"destination_ip","2001:db8::53","destination_port",53,
            "captured_length",80,"original_length",80,"status","decoded","udp_length",40,"udp_payload_declared_bytes",32,"udp_payload_captured_bytes",32,"udp_payload_complete",true,"udp_checksum_hex","0x1234",
            "timestamp",Json.object("nanoseconds_exact","1700000000250000000"),"dns",Json.object("id",42,"response",false,"rcode",0,"questions",new JSONArray().put(Json.object("name","example.test","type",1))));
        assertTrue(PacketPresentation.matches(p,"UDP","example.test"));assertFalse(PacketPresentation.matches(p,"TCP",""));assertEquals("[2001:db8::1]:53000",PacketPresentation.endpoint(p,"source"));
        String detail=PacketPresentation.detail(p);assertTrue(detail.contains("Question: example.test · A (IPv4 address)"));assertTrue(detail.contains("2023-11-14T22:13:20.250Z"));assertTrue(detail.contains("not verified"));assertTrue(detail.contains("No payload preview"));
    }
    public void testPreviewTextAndHexRemainExplicitRawEvidence() {
        JSONObject p=Json.object("protocol","UDP","protocols",new JSONArray().put("UDP"),"udp_payload_text","A\\x00B","udp_payload_hex","410042","udp_payload_preview_bytes",3,"udp_payload_preview_truncated",true);
        assertTrue(PacketPresentation.detail(p).contains("not decrypted content"));assertTrue(PacketPresentation.detail(p).contains("A\\x00B"));assertTrue(PacketPresentation.hex(p).contains("41 00 42"));assertTrue(PacketPresentation.hex(p).contains("Preview limited"));assertTrue(PacketPresentation.title(p).contains("application not decoded"));
    }
}
