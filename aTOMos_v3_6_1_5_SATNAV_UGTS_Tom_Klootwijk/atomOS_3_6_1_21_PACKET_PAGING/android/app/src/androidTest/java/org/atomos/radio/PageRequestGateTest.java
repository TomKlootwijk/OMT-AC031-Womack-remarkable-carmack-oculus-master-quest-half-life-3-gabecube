package org.atomos.radio;

import android.test.InstrumentationTestCase;

public final class PageRequestGateTest extends InstrumentationTestCase {
    public void testOldSearchCannotReplaceNewPage(){PageRequestGate gate=new PageRequestGate();long first=gate.begin();assertTrue(gate.accepts(first));long second=gate.begin();assertFalse(gate.accepts(first));assertTrue(gate.accepts(second));long third=gate.begin();assertFalse(gate.accepts(second));assertTrue(gate.accepts(third));}
    public void testDestroyedBrowserRejectsPendingAndFutureResults(){PageRequestGate old=new PageRequestGate();long request=old.begin();old.close();assertFalse(old.accepts(request));assertFalse(old.accepts(old.begin()));PageRequestGate recreated=new PageRequestGate();long current=recreated.begin();assertTrue(recreated.accepts(current));assertFalse(old.accepts(current));}
}
