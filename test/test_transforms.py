from __future__ import print_function
import os
import torch
import torchaudio
import torchaudio.transforms as transforms
import numpy as np
import unittest


class Tester(unittest.TestCase):

    # create a sinewave signal for testing
    sr = 16000
    freq = 440
    volume = .3
    sig = (torch.cos(2 * np.pi * torch.arange(0, 4 * sr).float() * freq / sr))
    sig.unsqueeze_(1)  # (64000, 1)
    sig = (sig * volume * 2**31).long()
    # file for stereo stft test
    test_dirpath = os.path.dirname(os.path.realpath(__file__))
    test_filepath = os.path.join(test_dirpath, "assets",
                                 "steam-train-whistle-daniel_simon.mp3")

    def test_scale(self):

        audio_orig = self.sig.clone()
        result = transforms.Scale()(audio_orig)
        self.assertTrue(result.min() >= -1. and result.max() <= 1.)

        maxminmax = np.abs(
            [audio_orig.min(), audio_orig.max()]).max().astype(np.float)
        result = transforms.Scale(factor=maxminmax)(audio_orig)
        self.assertTrue((result.min() == -1. or result.max() == 1.) and
                        result.min() >= -1. and result.max() <= 1.)

        repr_test = transforms.Scale()
        self.assertTrue(repr_test.__repr__())

    def test_pad_trim(self):

        audio_orig = self.sig.clone()
        length_orig = audio_orig.size(0)
        length_new = int(length_orig * 1.2)

        result = transforms.PadTrim(max_len=length_new, channels_first=False)(audio_orig)
        self.assertEqual(result.size(0), length_new)

        result = transforms.PadTrim(max_len=length_new, channels_first=True)(audio_orig.transpose(0, 1))
        self.assertEqual(result.size(1), length_new)

        audio_orig = self.sig.clone()
        length_orig = audio_orig.size(0)
        length_new = int(length_orig * 0.8)

        result = transforms.PadTrim(max_len=length_new, channels_first=False)(audio_orig)

        self.assertEqual(result.size(0), length_new)

        repr_test = transforms.PadTrim(max_len=length_new, channels_first=False)
        self.assertTrue(repr_test.__repr__())

    def test_downmix_mono(self):

        audio_L = self.sig.clone()
        audio_R = self.sig.clone()
        R_idx = int(audio_R.size(0) * 0.1)
        audio_R = torch.cat((audio_R[R_idx:], audio_R[:R_idx]))

        audio_Stereo = torch.cat((audio_L, audio_R), dim=1)

        self.assertTrue(audio_Stereo.size(1) == 2)

        result = transforms.DownmixMono(channels_first=False)(audio_Stereo)

        self.assertTrue(result.size(1) == 1)

        repr_test = transforms.DownmixMono(channels_first=False)
        self.assertTrue(repr_test.__repr__())

    def test_lc2cl(self):

        audio = self.sig.clone()
        result = transforms.LC2CL()(audio)
        self.assertTrue(result.size()[::-1] == audio.size())

        repr_test = transforms.LC2CL()
        self.assertTrue(repr_test.__repr__())

    def test_compose(self):

        audio_orig = self.sig.clone()
        length_orig = audio_orig.size(0)
        length_new = int(length_orig * 1.2)
        maxminmax = np.abs(
            [audio_orig.min(), audio_orig.max()]).max().astype(np.float)

        tset = (transforms.Scale(factor=maxminmax),
                transforms.PadTrim(max_len=length_new, channels_first=False))
        result = transforms.Compose(tset)(audio_orig)

        self.assertTrue(np.abs([result.min(), result.max()]).max() == 1.)

        self.assertTrue(result.size(0) == length_new)

        repr_test = transforms.Compose(tset)
        self.assertTrue(repr_test.__repr__())

    def test_mu_law_companding(self):

        quantization_channels = 256

        sig = self.sig.clone()
        sig = sig / torch.abs(sig).max()
        self.assertTrue(sig.min() >= -1. and sig.max() <= 1.)

        sig_mu = transforms.MuLawEncoding(quantization_channels)(sig)
        self.assertTrue(sig_mu.min() >= 0. and sig.max() <= quantization_channels)

        sig_exp = transforms.MuLawExpanding(quantization_channels)(sig_mu)
        self.assertTrue(sig_exp.min() >= -1. and sig_exp.max() <= 1.)

        repr_test = transforms.MuLawEncoding(quantization_channels)
        self.assertTrue(repr_test.__repr__())
        repr_test = transforms.MuLawExpanding(quantization_channels)
        self.assertTrue(repr_test.__repr__())

    def test_mel2(self):
        top_db = 80.
        s2db = transforms.SpectrogramToDB("power", top_db)

        audio_orig = self.sig.clone()  # (16000, 1)
        audio_scaled = transforms.Scale()(audio_orig)  # (16000, 1)
        audio_scaled = transforms.LC2CL()(audio_scaled)  # (1, 16000)
        mel_transform = transforms.MelSpectrogram()
        # check defaults
        spectrogram_torch = s2db(mel_transform(audio_scaled))  # (1, 319, 40)
        self.assertTrue(spectrogram_torch.dim() == 3)
        self.assertTrue(spectrogram_torch.ge(spectrogram_torch.max() - top_db).all())
        self.assertEqual(spectrogram_torch.size(-1), mel_transform.n_mels)
        # check correctness of filterbank conversion matrix
        self.assertTrue(mel_transform.fm.fb.sum(1).le(1.).all())
        self.assertTrue(mel_transform.fm.fb.sum(1).ge(0.).all())
        # check options
        kwargs = {"window": torch.hamming_window, "pad": 10, "ws": 500, "hop": 125, "n_fft": 800, "n_mels": 50}
        mel_transform2 = transforms.MelSpectrogram(**kwargs)
        spectrogram2_torch = s2db(mel_transform2(audio_scaled))  # (1, 506, 50)
        self.assertTrue(spectrogram2_torch.dim() == 3)
        self.assertTrue(spectrogram_torch.ge(spectrogram_torch.max() - top_db).all())
        self.assertEqual(spectrogram2_torch.size(-1), mel_transform2.n_mels)
        self.assertTrue(mel_transform2.fm.fb.sum(1).le(1.).all())
        self.assertTrue(mel_transform2.fm.fb.sum(1).ge(0.).all())
        # check on multi-channel audio
        x_stereo, sr_stereo = torchaudio.load(self.test_filepath)
        spectrogram_stereo = s2db(mel_transform(x_stereo))
        self.assertTrue(spectrogram_stereo.dim() == 3)
        self.assertTrue(spectrogram_stereo.size(0) == 2)
        self.assertTrue(spectrogram_torch.ge(spectrogram_torch.max() - top_db).all())
        self.assertEqual(spectrogram_stereo.size(-1), mel_transform.n_mels)
        # check filterbank matrix creation
        fb_matrix_transform = transforms.MelScale(n_mels=100, sr=16000, f_max=None, f_min=0., n_stft=400)
        self.assertTrue(fb_matrix_transform.fb.sum(1).le(1.).all())
        self.assertTrue(fb_matrix_transform.fb.sum(1).ge(0.).all())
        self.assertEqual(fb_matrix_transform.fb.size(), (400, 100))

    def test_mfcc(self):
        audio_orig = self.sig.clone()
        audio_scaled = transforms.Scale()(audio_orig)  # (16000, 1)
        audio_scaled = transforms.LC2CL()(audio_scaled)  # (1, 16000)

        sample_rate = 16000
        n_mfcc = 40
        n_mels = 128
        mfcc_transform = torchaudio.transforms.MFCC(sr=sample_rate,
                                                    n_mfcc=n_mfcc,
                                                    norm='ortho')
        # check defaults
        torch_mfcc = mfcc_transform(audio_scaled)
        self.assertTrue(torch_mfcc.dim() == 3)
        self.assertTrue(torch_mfcc.shape[2] == n_mfcc)
        self.assertTrue(torch_mfcc.shape[1] == 321)
        # check melkwargs are passed through
        melkwargs = {'ws': 200}
        mfcc_transform2 = torchaudio.transforms.MFCC(sr=sample_rate,
                                                     n_mfcc=n_mfcc,
                                                     norm='ortho',
                                                     melkwargs=melkwargs)
        torch_mfcc2 = mfcc_transform2(audio_scaled)
        self.assertTrue(torch_mfcc2.shape[1] == 641)

        # check norms work correctly
        mfcc_transform_norm_none = torchaudio.transforms.MFCC(sr=sample_rate,
                                                              n_mfcc=n_mfcc,
                                                              norm=None)
        torch_mfcc_norm_none = mfcc_transform_norm_none(audio_scaled)

        norm_check = torch_mfcc.clone()
        norm_check[:, :, 0] *= np.sqrt(n_mels) * 2
        norm_check[:, :, 1:] *= np.sqrt(n_mels / 2) * 2

        self.assertTrue(torch_mfcc_norm_none.allclose(norm_check))

    def test_librosa_consistency(self):
        try:
            import librosa
            import scipy
        except ImportError:
            return

        input_path = os.path.join(self.test_dirpath, 'assets', 'sinewave.wav')
        sound, sample_rate = torchaudio.load(input_path)
        sound_librosa = sound.cpu().numpy().squeeze().T  # squeeze batch and channel first

        n_fft = 400
        hop_length = 200
        power = 2.0
        n_mels = 128
        n_mfcc = 40
        sample_rate = 16000

        # test core spectrogram
        spect_transform = torchaudio.transforms.Spectrogram(n_fft=n_fft, hop=hop_length, power=2)
        out_librosa, _ = librosa.core.spectrum._spectrogram(y=sound_librosa,
                                                            n_fft=n_fft,
                                                            hop_length=hop_length,
                                                            power=2)

        out_torch = spect_transform(sound).squeeze().cpu().numpy().T
        self.assertTrue(np.allclose(out_torch, out_librosa, atol=1e-5))

        # test mel spectrogram
        melspect_transform = torchaudio.transforms.MelSpectrogram(sr=sample_rate, window=torch.hann_window,
                                                                  hop=hop_length, n_mels=n_mels, n_fft=n_fft)
        librosa_mel = librosa.feature.melspectrogram(y=sound_librosa, sr=sample_rate,
                                                     n_fft=n_fft, hop_length=hop_length, n_mels=n_mels,
                                                     htk=True, norm=None)
        torch_mel = melspect_transform(sound).squeeze().cpu().numpy().T

        # lower tolerance, think it's double vs. float
        self.assertTrue(np.allclose(torch_mel, librosa_mel, atol=5e-3))

        # test s2db

        db_transform = torchaudio.transforms.SpectrogramToDB("power", 80.)
        db_torch = db_transform(spect_transform(sound)).squeeze().cpu().numpy().T
        db_librosa = librosa.core.spectrum.power_to_db(out_librosa)
        self.assertTrue(np.allclose(db_torch, db_librosa, atol=5e-3))

        db_torch = db_transform(melspect_transform(sound)).squeeze().cpu().numpy().T
        db_librosa = librosa.core.spectrum.power_to_db(librosa_mel)

        self.assertTrue(np.allclose(db_torch, db_librosa, atol=5e-3))

        # test MFCC
        melkwargs = {'hop': hop_length, 'n_fft': n_fft}
        mfcc_transform = torchaudio.transforms.MFCC(sr=sample_rate,
                                                    n_mfcc=n_mfcc,
                                                    norm='ortho',
                                                    melkwargs=melkwargs)

        # librosa.feature.mfcc doesn't pass kwargs properly since some of the
        # kwargs for melspectrogram and mfcc are the same. We just follow the
        # function body in https://librosa.github.io/librosa/_modules/librosa/feature/spectral.html#melspectrogram
        # to mirror this function call with correct args:

#         librosa_mfcc = librosa.feature.mfcc(y=sound_librosa,
#                                             sr=sample_rate,
#                                             n_mfcc = n_mfcc,
#                                             hop_length=hop_length,
#                                             n_fft=n_fft,
#                                             htk=True,
#                                             norm=None,
#                                             n_mels=n_mels)

        librosa_mfcc = scipy.fftpack.dct(db_librosa, axis=0, type=2, norm='ortho')[:n_mfcc]
        torch_mfcc = mfcc_transform(sound).squeeze().cpu().numpy().T

        self.assertTrue(np.allclose(torch_mfcc, librosa_mfcc, atol=5e-3))


if __name__ == '__main__':
    unittest.main()
