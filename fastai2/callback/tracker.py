# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/17_callback.tracker.ipynb (unless otherwise specified).

__all__ = ['ShortEpochCallback', 'GradientAccumulation', 'TerminateOnNaNCallback', 'TrackerCallback',
           'EarlyStoppingCallback', 'SaveModelCallback', 'ReduceLROnPlateau']

# Cell
from ..basics import *
from .progress import *
from .fp16 import MixedPrecision

# Cell
class ShortEpochCallback(Callback):
    "Fit just `pct` of an epoch, then stop"
    def __init__(self,pct=0.01,short_valid=True): self.pct,self.short_valid = pct,short_valid
    def after_batch(self):
        if self.iter/self.n_iter < self.pct: return
        if self.training:    raise CancelTrainException
        if self.short_valid: raise CancelValidException

# Cell
class GradientAccumulation(Callback):
    "Accumulate gradients before updating weights"
    toward_end,run_before=True,MixedPrecision

    def __init__(self, n_items=32):
        store_attr(self, 'n_items')

    def begin_fit(self):
        self.count=0

    def after_backward(self):
        self.count += find_bs(self.learn.yb)
        if self.count < self.n_items:
            raise CancelBatchException() #skip weight update
        else:
            self.count=0

    _docs = dict(begin_fit="Set counter to 0",
                 after_backward="Skip weight update if we have not seen enough items"
    )

# Cell
class TerminateOnNaNCallback(Callback):
    "A `Callback` that terminates training if loss is NaN."
    run_before=Recorder

    def after_batch(self):
        "Test if `last_loss` is NaN and interrupts training."
        if torch.isinf(self.loss) or torch.isnan(self.loss): raise CancelFitException

# Cell
class TrackerCallback(Callback):
    "A `Callback` that keeps track of the best value in `monitor`."
    remove_on_fetch,run_after = True,Recorder

    def __init__(self, monitor='valid_loss', comp=None, min_delta=0.):
        if comp is None: comp = np.less if 'loss' in monitor or 'error' in monitor else np.greater
        if comp == np.less: min_delta *= -1
        self.monitor,self.comp,self.min_delta = monitor,comp,min_delta

    def begin_fit(self):
        "Prepare the monitored value"
        self.run = not hasattr(self, "lr_finder") and not hasattr(self, "gather_preds")
        self.best = float('inf') if self.comp == np.less else -float('inf')
        assert self.monitor in self.recorder.metric_names[1:]
        self.idx = list(self.recorder.metric_names[1:]).index(self.monitor)

    def after_epoch(self):
        "Compare the last value to the best up to know"
        val = self.recorder.values[-1][self.idx]
        if self.comp(val - self.min_delta, self.best): self.best,self.new_best = val,True
        else: self.new_best = False

    def after_fit(self): self.run=True

# Cell
class EarlyStoppingCallback(TrackerCallback):
    "A `TrackerCallback` that terminates training when monitored quantity stops improving."
    def __init__(self, monitor='valid_loss', comp=None, min_delta=0., patience=1):
        super().__init__(monitor=monitor, comp=comp, min_delta=min_delta)
        self.patience = patience

    def begin_fit(self): self.wait = 0; super().begin_fit()
    def after_epoch(self):
        "Compare the value monitored to its best score and maybe stop training."
        super().after_epoch()
        if self.new_best: self.wait = 0
        else:
            self.wait += 1
            if self.wait >= self.patience:
                print(f'No improvement since epoch {self.epoch-self.wait}: early stopping')
                raise CancelFitException()

# Cell
class SaveModelCallback(TrackerCallback):
    "A `TrackerCallback` that saves the model's best during training and loads it at the end."
    def __init__(self, monitor='valid_loss', comp=None, min_delta=0., fname='model', every_epoch=False, add_save=None, with_opt=False):
        super().__init__(monitor=monitor, comp=comp, min_delta=min_delta)
        store_attr(self, 'fname,every_epoch,add_save,with_opt')

    def _save(self, name):
        self.learn.save(name, with_opt=self.with_opt)
        if self.add_save is not None:
            with self.add_save.open('wb') as f: self.learn.save(f, with_opt=self.with_opt)

    def after_epoch(self):
        "Compare the value monitored to its best score and save if best."
        if self.every_epoch: self._save(f'{self.fname}_{self.epoch}')
        else: #every improvement
            super().after_epoch()
            if self.new_best: self._save(f'{self.fname}')

    def after_fit(self, **kwargs):
        "Load the best model."
        if not self.every_epoch: self.learn.load(f'{self.fname}')

# Cell
class ReduceLROnPlateau(TrackerCallback):
    "A `TrackerCallback` that reduces learning rate when a metric has stopped improving."
    def __init__(self, monitor='valid_loss', comp=None, min_delta=0., patience=1, factor=10.):
        super().__init__(monitor=monitor, comp=comp, min_delta=min_delta)
        self.patience,self.factor = patience,factor

    def begin_fit(self): self.wait = 0; super().begin_fit()
    def after_epoch(self):
        "Compare the value monitored to its best score and reduce LR by `factor` if no improvement."
        super().after_epoch()
        if self.new_best: self.wait = 0
        else:
            self.wait += 1
            if self.wait >= self.patience:
                for h in self.opt.hypers: h['lr'] /= self.factor
                self.wait = 0
                print(f'Epoch {self.epoch}: reducing lr to {self.opt.hypers[-1]["lr"]}')