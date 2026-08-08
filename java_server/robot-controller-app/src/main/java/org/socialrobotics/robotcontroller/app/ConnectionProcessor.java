package org.socialrobotics.robotcontroller.app;

import java.io.IOException;
import java.net.Socket;

/** Owns protocol processing for one accepted client socket. */
interface ConnectionProcessor {
    void process(Socket socket) throws IOException;
}
