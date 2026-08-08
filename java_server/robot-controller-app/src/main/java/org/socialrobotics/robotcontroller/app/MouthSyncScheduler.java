package org.socialrobotics.robotcontroller.app;

/** Injectable scheduler seam for playhead-based mouth synchronization. */
interface MouthSyncScheduler extends AutoCloseable {
    MouthSyncHandle schedule(Runnable task);

    @Override
    void close();
}
