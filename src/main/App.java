package main;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import utils.PoseExecutorThread;


public class App {

	/*
	 * play_wav
	 * stop_wav
	 * play_pose
	 * stop_pose
	 * play_motion
	 * stop_motion
	 * read_axes
	 */

	public static void main(String[] args) {
		ExecutorService service = Executors.newFixedThreadPool(2);
		service.execute(new TCPServer(Params.port));
		service.execute(new PoseExecutorThread());
	}
}

