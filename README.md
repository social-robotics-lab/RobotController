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

