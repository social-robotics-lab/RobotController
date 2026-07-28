# RobotController

This is a tcp-server program for controlling a robot (Sota or CommU).

A sample client program is [here](https://github.com/social-robotics-lab/robotcontroller_client).

If you want a binary program (jar file), you can download it from [RobotController_bin](https://github.com/social-robotics-lab/RobotController_bin).


# Java version
JavaSE-1.8

# Usage
- Build a JAR file by using eclipse.
- Move the JAR file into a directory of Sota (CommU).
- Edit System.properties (e.g. Port settings, etc)
- Run the JAR file: `java -jar RobotController.jar`, then the server will run.
- Connect to the server by a client

# Build a JAR file
You need the following libraries.
- core-2.2.jar
- gson-2.8.5.jar
- javase-2.2.jar
- jna-4.1.0.jar
- json-20180813.jar
- sotalib.jar (You can get it from https://github.com/vstoneofficial/SotaSample)


## Protocol

This server can accept the following commands:
- play_wav *wav*
- stop_wav
- play_pose *pose*
- stop_pose
- play_motion *motion*
- stop_motion
- play_idle_motion *speed*
- stop_idle_motion
- read_axes


This server communicates with the client in two stages as follows.
1. The client sends the size of the message to be sent as an int type (4 byte).
2. The client sends the message.

For example, if you use play_wav command, you should send message as follows:
1. The client sends the size of the string "play_wav".
2. The client sends the string "play_wav".
3. The client sends the size of the wav data.
4. The client sends the wav data.

## Python version

The Python implementation is under `python_server/` and targets CPython
3.6.15. The safe Mock Server remains the default development composition.

The Sota standard-backend foundation communicates with the existing
`vsmd_edison` daemon at `127.0.0.1:6498`; it does not open Futaba UART or I2C
devices directly. On 2026-07-28, the read-only probe completed successfully
from Windows 11 / Python 3.14.3 through an SSH local port forward to the Intel
Edison. A human operator may run it as follows:

```powershell
cd C:\Users\tiio\Workspace\RobotController\python_server
py -3.14 -m robot_controller.hardware.vsmd.probe
```

The probe connects and reads the server banner, mouth selector, AudioDiff,
mouth interpolation Target/Output, and ServoReadPos. It has no memory-write
option. Automated agents and automated tests must not run it against a real
robot. The successful trial sent no VSMD write request and caused no observed
servo or LED state change. It does not enable production mouth-LED control or
connect `VsmdSotaCommandTarget` to the default Composition Root; Mock remains
the default Backend.

The VSMD memory-write line was verified from a PCAP capture of
`sotalib.jar`. It uses one ASCII space between every field:

```text
w 0124 9c 0c\r\n
```

The general form is lower-case `w`, a four-digit lower-case hexadecimal
address, and one or more two-digit lower-case hexadecimal bytes, all separated
by exactly one space and terminated by CRLF. Write requests have no response.
The Python API accepts an integer byte count, but the VSMD wire size token is
lower-case hexadecimal. For example, 64 bytes is `R 0e80 40\r\n`; sending
`R 0e80 64\r\n` requests 100 bytes because VSMD interprets `64` as `0x64`.
Read responses may contain exactly one ASCII space after the final byte, as in
`#0124 8a 00 \r\n`. The Codec accepts zero or one trailing space but rejects
leading spaces, repeated spaces, tabs, malformed byte tokens, and size or
address mismatches.

The production mouth-LED path is intentionally unavailable until the exact
`InterpLockerClient` protocol is verified. Existing Futaba direct-control
code remains isolated for experiments and is not the standard Sota Backend.
See `docs/sota-backend-design.md` for the trial record and current completion
boundary, and `docs/protocol-compatibility.md` for the measured wire protocol
and memory values.

