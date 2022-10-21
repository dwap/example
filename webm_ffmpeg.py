import subprocess
import numpy as np
import threading

import json
import ffmpeg
from ffmpeg._utils import convert_kwargs_to_cmd_line_args
from ffmpeg._run import Error


class webm_ffmpeg():
    def __init__(self) -> None:
        self._width = None
        self._height = None
        self._total_frame = None
        self._frame_rate = None

    @property
    def size(self):
        return self._width, self._height

    @property
    def frame_rate(self):
        return self._frame_rate

    def start_ffmpeg_process(self):
        vp9 = {"c:v": "libvpx-vp9"}
        args = (
            ffmpeg
                .input('pipe:', **vp9)
                .output('pipe:', format='rawvideo', pix_fmt='bgra')
                .run_async(pipe_stdout=True, pipe_stdin=True, pipe_stderr=subprocess.DEVNULL)
        )
        return args

    def read_frame(self, process):
        frame_size = self._height * self._width * 4
        in_bytes = process.stdout.read(frame_size)
        if len(in_bytes) == 0:
            frame = None
        else:
            assert len(in_bytes) == frame_size
            frame = (
                np
                    .frombuffer(in_bytes, np.uint8)
                    .reshape([self._height, self._width, 4])
            )
        return frame

    def writer(self, decoder_process, stream):
        try:
            decoder_process.stdin.write(stream)
        except (BrokenPipeError, OSError):
            # get_in_memory_video_frame_size causes BrokenPipeError exception and OSError exception.
            # This in not a clean solution, but it's the simplest I could find.
            return
        decoder_process.stdin.close()

    def load_webm(self, buff):
        probe = self.probe('pipe:', input=buff)
        video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        self._width = int(video_info['width'])
        self._height = int(video_info['height'])
        self._frame_rate = int(video_info['r_frame_rate'].split('/')[0])
        process = self.start_ffmpeg_process()
        thread = threading.Thread(target=self.writer, args=(process, buff))
        thread.start()
        #process.communicate(input=buff)
        frames = []
        while True:
            in_frame = self.read_frame(process)
            if in_frame is None:
                break
            else:
                frames.append(in_frame)
        #process.stdin.close()
        process.wait()
        return frames

    def probe(self, filename, cmd='ffprobe', input=None, timeout=None, **kwargs):
        """Run ffprobe on the specified file and return a JSON representation of the output.

        Raises:
            :class:`ffmpeg.Error`: if ffprobe returns a non-zero exit code,
                an :class:`Error` is returned with a generic error message.
                The stderr output can be retrieved by accessing the
                ``stderr`` property of the exception.
        """
        args = [cmd, '-show_format', '-show_streams', '-of', 'json']
        args += convert_kwargs_to_cmd_line_args(kwargs)
        args += [filename]

        p = subprocess.Popen(
            args, stdin=None if input is None else subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate(input=input, timeout=timeout)
        if p.returncode != 0:
            raise Error('ffprobe', out, err)
        return json.loads(out.decode('utf-8'))
