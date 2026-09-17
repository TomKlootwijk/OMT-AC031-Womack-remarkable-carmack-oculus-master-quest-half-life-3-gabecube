package org.atomos.radio;

import android.os.Build;
import android.telephony.*;
import org.json.JSONObject;

final class CellEncoder {
    private CellEncoder() {}
    @SuppressWarnings("deprecation")
    static String sourceNs(CellInfo c) {
        return sourceNs(c.getTimeStamp(),Build.VERSION.SDK_INT >= 30 ? c.getTimestampMillis() : 0,Build.VERSION.SDK_INT);
    }
    static String sourceNs(long rawNanos,long millis,int sdk) {
        if(rawNanos==Long.MAX_VALUE) return null;
        long value = sdk >= 30 ? millis : rawNanos;
        if(value <= 0 || value == Long.MAX_VALUE) return null;
        if(sdk >= 30) {
            if(value > Long.MAX_VALUE / 1000000L) return null;
            value *= 1000000L;
        }
        return Long.toString(value);
    }
    static JSONObject encode(CellInfo c, int subscriptionId, String origin) {
        String rat; JSONObject identity, signal;
        if(c instanceof CellInfoNr) {
            CellIdentityNr i=(CellIdentityNr)((CellInfoNr)c).getCellIdentity(); CellSignalStrengthNr s=(CellSignalStrengthNr)((CellInfoNr)c).getCellSignalStrength(); rat="NR";
            identity=Json.object("mcc",i.getMccString(),"mnc",i.getMncString(),"nci",Json.identity(i.getNci()),"tac",Json.identity(i.getTac()),"pci",Json.identity(i.getPci()),"nrarfcn",Json.identity(i.getNrarfcn()));
            signal=Json.object("dbm",Json.metric(s.getDbm()),"ss_rsrp_dbm",Json.metric(s.getSsRsrp()),"ss_rsrq_db",Json.metric(s.getSsRsrq()),"ss_sinr_db",Json.metric(s.getSsSinr()),"csi_rsrp_dbm",Json.metric(s.getCsiRsrp()),"csi_rsrq_db",Json.metric(s.getCsiRsrq()),"csi_sinr_db",Json.metric(s.getCsiSinr()));
        } else if(c instanceof CellInfoLte) {
            CellIdentityLte i=((CellInfoLte)c).getCellIdentity(); CellSignalStrengthLte s=((CellInfoLte)c).getCellSignalStrength(); rat="LTE";
            identity=Json.object("mcc",i.getMccString(),"mnc",i.getMncString(),"ci",Json.identity(i.getCi()),"tac",Json.identity(i.getTac()),"pci",Json.identity(i.getPci()),"earfcn",Json.identity(i.getEarfcn()),"bandwidth_khz",Json.identity(i.getBandwidth()));
            // AOSP Android 10 stores tenths of dB; Android 11+ stores dB. Never infer units from magnitude.
            signal=Json.object("dbm",Json.metric(s.getDbm()),"rsrp_dbm",Json.metric(s.getRsrp()),"rsrq_db",Json.metric(s.getRsrq()),"rssi_dbm",Json.metric(s.getRssi()),"rssnr_api_raw",Json.metric(s.getRssnr()),"rssnr_api_unit",Build.VERSION.SDK_INT >= 30 ? "dB" : "0.1_dB",
                Build.VERSION.SDK_INT >= 30 ? "rssnr_db" : "rssnr_tenth_db",Json.metric(s.getRssnr()),"timing_advance_raw",Json.identity(s.getTimingAdvance()));
        } else if(c instanceof CellInfoWcdma) {
            CellIdentityWcdma i=((CellInfoWcdma)c).getCellIdentity(); CellSignalStrengthWcdma s=((CellInfoWcdma)c).getCellSignalStrength(); rat="WCDMA";
            identity=Json.object("mcc",i.getMccString(),"mnc",i.getMncString(),"cid",Json.identity(i.getCid()),"lac",Json.identity(i.getLac()),"psc",Json.identity(i.getPsc()),"uarfcn",Json.identity(i.getUarfcn()));
            signal=Json.object("dbm",Json.metric(s.getDbm()));
        } else if(c instanceof CellInfoGsm) {
            CellIdentityGsm i=((CellInfoGsm)c).getCellIdentity(); CellSignalStrengthGsm s=((CellInfoGsm)c).getCellSignalStrength(); rat="GSM";
            identity=Json.object("mcc",i.getMccString(),"mnc",i.getMncString(),"cid",Json.identity(i.getCid()),"lac",Json.identity(i.getLac()),"bsic",Json.identity(i.getBsic()),"arfcn",Json.identity(i.getArfcn()));
            signal=Json.object("dbm",Json.metric(s.getDbm()),"timing_advance_raw",Json.identity(s.getTimingAdvance()));
        } else if(c instanceof CellInfoTdscdma) {
            CellIdentityTdscdma i=((CellInfoTdscdma)c).getCellIdentity(); CellSignalStrengthTdscdma s=((CellInfoTdscdma)c).getCellSignalStrength(); rat="TDSCDMA";
            identity=Json.object("mcc",i.getMccString(),"mnc",i.getMncString(),"cid",Json.identity(i.getCid()),"lac",Json.identity(i.getLac()),"cpid",Json.identity(i.getCpid()),"uarfcn",Json.identity(i.getUarfcn()));
            signal=Json.object("dbm",Json.metric(s.getDbm()),"rscp_dbm",Json.metric(s.getRscp()));
        } else if(c instanceof CellInfoCdma) {
            CellIdentityCdma i=((CellInfoCdma)c).getCellIdentity(); CellSignalStrengthCdma s=((CellInfoCdma)c).getCellSignalStrength(); rat="CDMA";
            identity=Json.object("network_id",Json.identity(i.getNetworkId()),"system_id",Json.identity(i.getSystemId()),"basestation_id",Json.identity(i.getBasestationId()));
            signal=Json.object("dbm",Json.metric(s.getDbm()),"cdma_dbm",Json.metric(s.getCdmaDbm()),"evdo_dbm",Json.metric(s.getEvdoDbm()));
        } else { rat=c.getClass().getSimpleName(); identity=Json.object(); signal=Json.object(); }
        return Json.object("subscription_id", subscriptionId < 0 ? null : subscriptionId,"rat",rat,
            "registered",c.isRegistered(),"connection_status",c.getCellConnectionStatus(),"identity",identity,"signal",signal,
            "origin",origin,"subscription_scope",origin.equals("initial_cache") ? "device_wide" : subscriptionId < 0 ? "default_unspecified" : "query_context",
            "source_timestamp_unit",Build.VERSION.SDK_INT >= 30 ? "ms" : "ns");
    }
}
