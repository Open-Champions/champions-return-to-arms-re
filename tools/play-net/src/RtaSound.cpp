// Sound output. See Rta.h.
//
// Play!'s sound handler for macOS (CSH_OpenAL) queues each block of sound as it is
// handed over and starts the source when it finds it stopped. Nothing keeps a reserve:
// how much sound lies between the machine and the loudspeaker is whatever was there
// when the source last started. If that is little, every frame that is a few
// milliseconds late leaves the source without sound (a click, a gap); and because the
// machine, timed by the display, makes sound a little faster than the sound device
// plays it (60.00 frames a second where the console has 59.94), the queue then grows by
// a millisecond every second until all 25 buffers are full - three quarters of a second
// behind the picture - and blocks are thrown away from then on.
//
// This handler keeps a reserve on purpose. The source is started when a set amount of
// sound is queued (the block and 40 ms), and from then on the amount is held there by
// making the sound a very little shorter or longer before it is queued (at most half a
// per cent, a twelfth of a semitone; four-point interpolation, in step from block to
// block). The source's own pitch setting is not used for this: set again for every
// block it did not hold the amount. When the source does run dry - a frame that took
// far too long, a level being loaded - it is started again with the full reserve.
// Every such event is counted.
//
// --rta-sound-plain makes it queue as Play! does (for comparing); --rta-sound-wav writes
// everything the machine hands over to a WAV file in the data directory.
#include "Rta.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <deque>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

#ifdef __APPLE__
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
#include <OpenAL/al.h>
#include <OpenAL/alc.h>
#else
#include <AL/al.h>
#include <AL/alc.h>
#endif

#include "sound/SoundHandler.h"

namespace
{
	struct Config
	{
		bool wav = false;
		bool plain = false;
		bool muted = false;
		std::string directory;
	};
	Config g_config;

	struct Stats
	{
		uint64 blocks = 0;        // handed over by the machine
		uint64 frames = 0;        // stereo sample pairs in them
		uint64 starts = 0;        // times the source was started
		uint64 underruns = 0;     // times it was found to have run dry
		double underrunMs = 0;    // how long it was dry, in all (from the clock)
		double underrunMaxMs = 0; // the longest
		uint64 overruns = 0;      // blocks thrown away: no buffer free
		uint64 dropped = 0;       // blocks thrown away: too much queued
		uint64 clipped = 0;       // samples at either end of the scale
		uint64 clippedRuns = 0;   // runs of three or more of those in a channel
		uint64 silentBlocks = 0;  // blocks of nothing but zero
		int peak = 0;
		double depthMin = 1e9, depthMax = 0, depthSum = 0; // ms queued right after a block was added, while playing
		uint64 depthCount = 0;
		double lowMin = 1e9;                   // ms left right before a block was added, while playing
		double pitchMin = 1, pitchMax = 1;
		uint64 firstUs = 0, lastUs = 0; // clock of the first and the last block
		unsigned int sampleRate = 0;
		unsigned int blockFrames = 0;
	};
	std::mutex g_mutex;
	Stats g_stats;
	std::string g_wavPath;

	uint64 NowUs()
	{
		return static_cast<uint64>(std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
	}

	class CSoundRta : public CSoundHandler
	{
	public:
		enum
		{
			MAX_BUFFERS = 32,
			RESERVE_MS = 40, // queued beyond one block when the source is started, and held
		};

		CSoundRta()
		{
			m_device = alcOpenDevice(nullptr);
			if(!m_device) throw std::runtime_error("no sound device");
			const ALCint attributes[] = {ALC_FREQUENCY, 44100, 0, 0};
			m_context = alcCreateContext(m_device, attributes);
			if(!m_context)
			{
				alcCloseDevice(m_device);
				throw std::runtime_error("no sound context");
			}
			alcMakeContextCurrent(m_context);
			alGenSources(1, &m_source);
			alGenBuffers(MAX_BUFFERS, m_buffers);
			// a test run on a computer somebody is using makes no noise; nothing else differs
			if(g_config.muted) alSourcef(m_source, AL_GAIN, 0.0f);
			Reset();
			if(g_config.wav) OpenWav();
		}

		~CSoundRta() override
		{
			alcMakeContextCurrent(m_context);
			alSourceStop(m_source);
			alSourcei(m_source, AL_BUFFER, 0);
			alDeleteSources(1, &m_source);
			alDeleteBuffers(MAX_BUFFERS, m_buffers);
			alcMakeContextCurrent(nullptr);
			alcDestroyContext(m_context);
			alcCloseDevice(m_device);
			CloseWav();
		}

		void Reset() override
		{
			alSourceStop(m_source);
			alSourcei(m_source, AL_BUFFER, 0);
			alSourcef(m_source, AL_PITCH, 1.0f);
			m_free.assign(m_buffers, m_buffers + MAX_BUFFERS);
			m_queued.clear();
			m_queuedFrames = 0;
			m_playing = false;
			m_pitch = 1;
		}

		bool HasFreeBuffers() override
		{
			return !m_free.empty();
		}

		void RecycleBuffers() override
		{
			ALint processed = 0;
			alGetSourcei(m_source, AL_BUFFERS_PROCESSED, &processed);
			while((processed-- > 0) && !m_queued.empty())
			{
				ALuint buffer = 0;
				alSourceUnqueueBuffers(m_source, 1, &buffer);
				if(alGetError() != AL_NO_ERROR) break;
				m_queuedFrames -= m_queued.front().second;
				m_queued.pop_front();
				m_free.push_back(buffer);
			}
		}

		void Write(int16* samples, unsigned int sampleCount, unsigned int sampleRate) override
		{
			unsigned int frames = sampleCount / 2;
			if(frames == 0) return;
			uint64 now = NowUs();
			double blockMs = (frames * 1000.0) / sampleRate;
			if(m_wav)
			{
				if(fwrite(samples, sizeof(int16), sampleCount, m_wav) == sampleCount) m_wavBytes += static_cast<uint64>(sampleCount) * sizeof(int16);
				if((++m_wavBlocks % 64) == 0) FinishWavHeader();
			}

			std::lock_guard<std::mutex> lock(g_mutex);
			auto& s = g_stats;
			s.blocks++;
			s.frames += frames;
			s.sampleRate = sampleRate;
			s.blockFrames = frames;
			if(s.firstUs == 0) s.firstUs = now;
			s.lastUs = now;
			{
				bool silent = true;
				int run[2] = {0, 0};
				for(unsigned int i = 0; i < sampleCount; i++)
				{
					int value = samples[i];
					if(value != 0) silent = false;
					int size = (value < 0) ? -value : value;
					if(size > s.peak) s.peak = size;
					if((value >= 32767) || (value <= -32768))
					{
						s.clipped++;
						if(++run[i & 1] == 3) s.clippedRuns++;
					}
					else
						run[i & 1] = 0;
				}
				if(silent) s.silentBlocks++;
			}

			// has the source run dry since the last block?
			ALint state = AL_INITIAL;
			alGetSourcei(m_source, AL_SOURCE_STATE, &state);
			if(m_playing && (state != AL_PLAYING))
			{
				m_playing = false;
				s.underruns++;
				double dryMs = ((now - m_lastWriteUs) / 1000.0) - (m_depthAfterLastWrite / m_pitch);
				if(dryMs < 0) dryMs = 0;
				s.underrunMs += dryMs;
				if(dryMs > s.underrunMaxMs) s.underrunMaxMs = dryMs;
				// A stopped source has played everything it had. It is put back to its
				// first state: to a stopped source every buffer that is queued counts
				// as played at once, and the reserve could never be built up again.
				RecycleBuffers();
				alSourceRewind(m_source);
			}

			double depthBefore = Depth(sampleRate);
			double target = blockMs + RESERVE_MS;
			if(m_playing && !g_config.plain)
			{
				if(depthBefore < s.lowMin) s.lowMin = depthBefore;
				if(depthBefore > (target + (3 * blockMs)))
				{
					// far too much queued (the machine ran ahead): this block is left out
					s.dropped++;
					return;
				}
			}
			if(m_free.empty())
			{
				s.overruns++;
				return;
			}
			// How fast this block is to be used up: 10 ms too much queued, 0.1 % faster;
			// never more than half a per cent either way
			const int16* out = samples;
			unsigned int outFrames = frames;
			if(!g_config.plain)
			{
				if(m_playing)
				{
					m_smoothed += 0.1 * ((depthBefore + blockMs) - m_smoothed);
					double rate = 1.0 + ((m_smoothed - target) * 0.0001);
					if(rate > 1.005) rate = 1.005;
					if(rate < 0.995) rate = 0.995;
					m_rate = rate;
					if(m_rate < s.pitchMin) s.pitchMin = m_rate;
					if(m_rate > s.pitchMax) s.pitchMax = m_rate;
				}
				else
					m_rate = 1.0;
				outFrames = Resample(samples, frames);
				out = m_resampled.data();
				if(outFrames == 0) return;
			}
			ALuint buffer = m_free.front();
			m_free.pop_front();
			alBufferData(buffer, AL_FORMAT_STEREO16, out, outFrames * 2 * sizeof(int16), sampleRate);
			alSourceQueueBuffers(m_source, 1, &buffer);
			m_queued.emplace_back(buffer, outFrames);
			m_queuedFrames += outFrames;
			double depth = depthBefore + ((outFrames * 1000.0) / sampleRate);

			if(!m_playing)
			{
				if(g_config.plain || (depth >= target))
				{
					alSourcePlay(m_source);
					m_playing = true;
					m_smoothed = depth;
					s.starts++;
				}
			}
			else
			{
				if(depth < s.depthMin) s.depthMin = depth;
				if(depth > s.depthMax) s.depthMax = depth;
				s.depthSum += depth;
				s.depthCount++;
			}
			m_lastWriteUs = now;
			m_depthAfterLastWrite = depth;
		}

	private:
		// The block, used up 'm_rate' times as fast: frames in, frames out, the place
		// between two frames carried over from block to block. Each frame out is taken
		// from four frames in (Catmull-Rom), so that the high notes do not waver as the
		// place drifts.
		unsigned int Resample(const int16* samples, unsigned int frames)
		{
			// three frames of the past in front, as they were left
			m_input.insert(m_input.end(), samples, samples + (static_cast<size_t>(frames) * 2));
			size_t available = m_input.size() / 2;
			m_resampled.clear();
			// the frame out at place p needs frames floor(p) - 1 .. floor(p) + 2
			while((static_cast<size_t>(m_place) + 2) < available)
			{
				size_t index = static_cast<size_t>(m_place);
				double t = m_place - static_cast<double>(index);
				for(int channel = 0; channel < 2; channel++)
				{
					double p0 = m_input[((index - 1) * 2) + channel], p1 = m_input[(index * 2) + channel];
					double p2 = m_input[((index + 1) * 2) + channel], p3 = m_input[((index + 2) * 2) + channel];
					double value = p1 + (0.5 * t * ((p2 - p0) + (t * (((2.0 * p0) - (5.0 * p1) + (4.0 * p2) - p3) + (t * ((3.0 * (p1 - p2)) + p3 - p0))))));
					long rounded = std::lround(value);
					m_resampled.push_back(static_cast<int16>(rounded > 32767 ? 32767 : (rounded < -32768 ? -32768 : rounded)));
				}
				m_place += m_rate;
			}
			// keep what the next block still needs: from one frame before the place
			size_t keepFrom = static_cast<size_t>(m_place) - 1;
			if(keepFrom > available) keepFrom = available;
			m_input.erase(m_input.begin(), m_input.begin() + (keepFrom * 2));
			m_place -= static_cast<double>(keepFrom);
			return static_cast<unsigned int>(m_resampled.size() / 2);
		}

		// milliseconds of sound queued and not yet played
		double Depth(unsigned int sampleRate)
		{
			if(m_queued.empty()) return 0;
			ALint offset = 0;
			alGetSourcei(m_source, AL_SAMPLE_OFFSET, &offset);
			double left = static_cast<double>(m_queuedFrames) - static_cast<double>(offset);
			if(left < 0) left = 0;
			return (left * 1000.0) / sampleRate;
		}

		void OpenWav()
		{
			char stamp[32];
			time_t now = time(nullptr);
			strftime(stamp, sizeof(stamp), "%Y%m%d-%H%M%S", localtime(&now));
			std::string path = g_config.directory + "/sound-" + stamp + ".wav";
			m_wav = fopen(path.c_str(), "wb");
			if(!m_wav) return;
			uint8 header[44];
			memset(header, 0, sizeof(header));
			fwrite(header, 1, sizeof(header), m_wav);
			m_wavBytes = 0;
			{
				std::lock_guard<std::mutex> lock(g_mutex);
				g_wavPath = path;
			}
			Rta::LogLine("sound: the mixed output is being written to " + path);
		}

		void FinishWavHeader()
		{
			if(!m_wav) return;
			uint8 header[44];
			auto put32 = [&](int at, uint32 value) { memcpy(header + at, &value, 4); };
			auto put16 = [&](int at, uint16 value) { memcpy(header + at, &value, 2); };
			memcpy(header + 0, "RIFF", 4);
			put32(4, static_cast<uint32>(36 + m_wavBytes));
			memcpy(header + 8, "WAVEfmt ", 8);
			put32(16, 16);
			put16(20, 1);
			put16(22, 2);
			put32(24, 44100);
			put32(28, 44100 * 4);
			put16(32, 4);
			put16(34, 16);
			memcpy(header + 36, "data", 4);
			put32(40, static_cast<uint32>(m_wavBytes));
			long at = ftell(m_wav);
			fseek(m_wav, 0, SEEK_SET);
			fwrite(header, 1, sizeof(header), m_wav);
			fseek(m_wav, at, SEEK_SET);
			fflush(m_wav);
		}

		void CloseWav()
		{
			if(!m_wav) return;
			FinishWavHeader();
			fclose(m_wav);
			m_wav = nullptr;
		}

		ALCdevice* m_device = nullptr;
		ALCcontext* m_context = nullptr;
		ALuint m_source = 0;
		ALuint m_buffers[MAX_BUFFERS];
		std::deque<ALuint> m_free;
		std::deque<std::pair<ALuint, unsigned int>> m_queued;
		uint64 m_queuedFrames = 0;
		bool m_playing = false;
		double m_pitch = 1;
		double m_smoothed = 0;
		double m_rate = 1;
		double m_place = 1; // between frames of m_input; frame 0 is the past
		std::vector<int16> m_input = std::vector<int16>(2, 0);
		std::vector<int16> m_resampled;
		uint64 m_lastWriteUs = 0;
		double m_depthAfterLastWrite = 0;
		FILE* m_wav = nullptr;
		uint64 m_wavBytes = 0;
		uint64 m_wavBlocks = 0;
	};
}

void Rta::ConfigureSound(bool wav, bool plain, bool muted, const std::string& directory)
{
	g_config.wav = wav;
	g_config.plain = plain;
	g_config.muted = muted;
	g_config.directory = directory;
}

CSoundHandler::FactoryFunction Rta::GetSoundHandlerFactory()
{
	return []() -> CSoundHandler* { return new CSoundRta(); };
}

std::string Rta::SoundReport(bool reset)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	const auto& s = g_stats;
	char text[1024];
	double seconds = (s.lastUs - s.firstUs) / 1e6;
	// the first block is not in the span: n blocks span n - 1 block times
	double made = (s.blocks > 1) ? (static_cast<double>(s.frames - s.blockFrames) / (s.sampleRate ? s.sampleRate : 44100)) : 0;
	snprintf(text, sizeof(text),
	         "mode=%s blocks=%llu block_ms=%.1f sound_s=%.3f clock_s=%.3f sound_per_clock=%.5f starts=%llu underruns=%llu underrun_ms=%.1f underrun_max_ms=%.1f overruns=%llu dropped=%llu "
	         "queued_ms_min=%.1f queued_ms_avg=%.1f queued_ms_max=%.1f low_ms_min=%.1f rate_min=%.4f rate_max=%.4f peak=%d clipped=%llu clipped_runs=%llu silent_blocks=%llu wav=%s",
	         g_config.plain ? "plain" : "held", static_cast<unsigned long long>(s.blocks), s.sampleRate ? (s.blockFrames * 1000.0 / s.sampleRate) : 0.0, made, seconds, (seconds > 0) ? (made / seconds) : 0.0,
	         static_cast<unsigned long long>(s.starts), static_cast<unsigned long long>(s.underruns), s.underrunMs, s.underrunMaxMs, static_cast<unsigned long long>(s.overruns), static_cast<unsigned long long>(s.dropped),
	         s.depthCount ? s.depthMin : 0.0, s.depthCount ? (s.depthSum / s.depthCount) : 0.0, s.depthMax, (s.lowMin < 1e8) ? s.lowMin : 0.0, s.pitchMin, s.pitchMax, s.peak,
	         static_cast<unsigned long long>(s.clipped), static_cast<unsigned long long>(s.clippedRuns), static_cast<unsigned long long>(s.silentBlocks), g_wavPath.empty() ? "-" : g_wavPath.c_str());
	std::string result = text;
	if(reset) g_stats = Stats();
	return result;
}
