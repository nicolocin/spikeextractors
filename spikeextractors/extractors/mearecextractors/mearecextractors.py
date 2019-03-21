from spikeextractors import RecordingExtractor
from spikeextractors import SortingExtractor

import numpy as np
from pathlib import Path


def _load_required_modules():
    try:
        import MEArec as mr
        import quantities as pq
        import neo
    except ModuleNotFoundError:
        raise ModuleNotFoundError("To use the MEArec extractors, install MEArec: \n\n"
                                  "pip install MEArec\n\n")
    return mr, pq, neo


class MEArecRecordingExtractor(RecordingExtractor):
    def __init__(self, recording_path):
        RecordingExtractor.__init__(self)
        self._recording_path = recording_path
        self._fs = None
        self._positions = None
        self._recordings = None
        self._filehandle = None
        self._initialize()

        if self._locations is not None:
            for chan, pos in enumerate(self._locations):
                self.setChannelProperty(chan, 'location', pos)

    def _initialize(self):
        mr, pq, neo = _load_required_modules()
        recgen = mr.load_recordings(recordings=self._recording_path, return_h5_objects=True)
        self._fs = recgen.info['recordings']['fs']
        self._recordings = recgen.recordings
        self._num_channels, self._num_frames = np.array(self._recordings).shape
        if len(np.array(recgen.channel_positions)) == self._num_channels:
            self._locations = np.array(recgen.channel_positions)
        else:
            self._locations = None

    def getChannelIds(self):
        return list(range(self._num_channels))

    def getNumFrames(self):
        return self._num_frames

    def getSamplingFrequency(self):
        return self._fs

    def getTraces(self, channel_ids=None, start_frame=None, end_frame=None):
        if start_frame is None:
            start_frame = 0
        if end_frame is None:
            end_frame = self.getNumFrames()
        if channel_ids is None:
            channel_ids = range(self.getNumChannels())
        return self._recordings[channel_ids, start_frame:end_frame]

    @staticmethod
    def writeRecording(recording, save_path):
        '''
        Save recording extractor to MEArec format.
        Parameters
        ----------
        recording: RecordingExtractor
            Recording extractor object to be saved
        save_path: str
            .h5 or .hdf5 path
        '''
        mr, pq, neo = _load_required_modules()
        save_path = Path(save_path)
        if save_path.is_dir():
            print("The file will be saved as recording.h5 in the provided folder")
            save_path = save_path / 'recording.h5'
        if save_path.suffix == '.h5' or save_path.suffix == '.hdf5':
            info = {'recordings': {'fs': recording.getSamplingFrequency()}}
            rec_dict = {'recordings': recording.getTraces()}
            if 'location' in recording.getChannelPropertyNames():
                positions = np.array([recording.getChannelProperty(chan, 'location')
                                      for chan in recording.getChannelIds()])
                rec_dict['channel_positions'] = positions
            recgen = mr.RecordingGenerator(rec_dict=rec_dict, info=info)
            mr.save_recording_generator(recgen, str(save_path), verbose=False)
        else:
            raise Exception("Provide a folder or an .h5/.hdf5 as 'save_path'")


class MEArecSortingExtractor(SortingExtractor):
    def __init__(self, recording_path):
        SortingExtractor.__init__(self)
        self._recording_path = recording_path
        self._num_units = None
        self._spike_trains = None
        self._unit_ids = None
        self._fs = None
        self._initialize()

    def _initialize(self):
        mr, pq, neo = _load_required_modules()
        recgen = mr.load_recordings(recordings=self._recording_path)
        self._num_units = len(recgen.spiketrains)
        if 'unit_id' in recgen.spiketrains[0].annotations:
            self._unit_ids = [int(st.annotations['unit_id']) for st in recgen.spiketrains]
        else:
            self._unit_ids = list(range(self._num_units))
        self._spike_trains = recgen.spiketrains
        self._fs = recgen.info['recordings']['fs'] * pq.Hz  # fs is in kHz

        if 'soma_position' in self._spike_trains[0].annotations:
            for u, st in zip(self._unit_ids, self._spike_trains):
                self.setUnitProperty(u, 'soma_location', st.annotations['soma_position'])

    def getUnitIds(self):
        if self._unit_ids is None:
            self._initialize()
        return self._unit_ids

    def getNumUnits(self):
        if self._num_units is None:
            self._initialize()
        return self._num_units

    def getUnitSpikeTrain(self, unit_id, start_frame=None, end_frame=None):
        if start_frame is None:
            start_frame = 0
        if end_frame is None:
            end_frame = np.Inf
        if self._spike_trains is None:
            self._initialize()
        times = (self._spike_trains[self.getUnitIds().index(unit_id)].times.rescale('s') *
                 self._fs.rescale('Hz')).magnitude
        inds = np.where((start_frame <= times) & (times < end_frame))
        return np.rint(times[inds]).astype(int)

    @staticmethod
    def writeSorting(sorting, save_path, sampling_frequency):
        '''
        Save sorting extractor to MEArec format.
        Parameters
        ----------
        sorting: SortingExtractor
            Sorting extractor object to be saved
        save_path: str
            .h5 or .hdf5 path
        sampling_frequency: int
            Sampling frequency in Hz

        '''
        mr, pq, neo = _load_required_modules()
        save_path = Path(save_path)
        if save_path.is_dir():
            print("The file will be saved as sorting.h5 in the provided folder")
            save_path = save_path / 'sorting.h5'
        if save_path.suffix == '.h5' or save_path.suffix == '.hdf5':
            # create neo spike trains
            spiketrains = []
            for u in sorting.getUnitIds():
                st = neo.SpikeTrain(times=sorting.getUnitSpikeTrain(u) / float(sampling_frequency) * pq.s,
                                    t_start=np.min(sorting.getUnitSpikeTrain(u) / float(sampling_frequency)) * pq.s,
                                    t_stop=np.max(sorting.getUnitSpikeTrain(u) / float(sampling_frequency)) * pq.s)
                st.annotate(unit_id=u)
                spiketrains.append(st)

            info = {'recordings': {'fs': sampling_frequency}}
            rec_dict = {'spiketrains': spiketrains}
            recgen = mr.RecordingGenerator(rec_dict=rec_dict, info=info)
            mr.save_recording_generator(recgen, str(save_path), verbose=False)
        else:
            raise Exception("Provide a folder or an .h5/.hdf5 as 'save_path'")

