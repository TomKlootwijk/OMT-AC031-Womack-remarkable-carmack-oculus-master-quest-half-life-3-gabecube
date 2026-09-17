package org.atomos.radio;

/** Rejects old asynchronous results after another search, recreation or leaving the browser. */
final class PageRequestGate {
    private long generation;
    private boolean closed;
    synchronized long begin(){return ++generation;}
    synchronized boolean accepts(long candidate){return !closed && candidate==generation;}
    synchronized void close(){closed=true;generation++;}
}
