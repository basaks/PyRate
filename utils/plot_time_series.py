#!/usr/bin/python3

'''
This script has been copied from LiCSBAS package and modified for PyRate package.
See: https://github.com/yumorishita/LiCSBAS/blob/master/bin/LiCSBAS_plot_ts.py
'''

# plotting PyRate velocity and ts files
import rasterio
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, RadioButtons, RectangleSelector, CheckButtons
import matplotlib.dates as mdates
import matplotlib.backend_bases
import numpy as np
import fnmatch
import os
import statsmodels.api as sm
import xarray as xr
from datetime import datetime as dt
import warnings

# %% Calc model
def calc_model(dph, imdates_ordinal, xvalues, model):
    imdates_years = np.divide(imdates_ordinal,365.25) # imdates_ordinal / 365.25  ## dont care abs
    xvalues_years = xvalues / 365.25

    # models = ['Linear', 'Annual+L', 'Quad', 'Annual+Q']
    A = sm.add_constant(imdates_years)  # [1, t]
    An = sm.add_constant(xvalues_years)  # [1, t]
    if model == 0:  # Linear
        pass
    if model == 1:  # Annual+L
        sin = np.sin(2 * np.pi * imdates_years)
        cos = np.cos(2 * np.pi * imdates_years)
        A = np.concatenate((A, sin[:, np.newaxis], cos[:, np.newaxis]), axis=1)
        sin = np.sin(2 * np.pi * xvalues_years)
        cos = np.cos(2 * np.pi * xvalues_years)
        An = np.concatenate((An, sin[:, np.newaxis], cos[:, np.newaxis]), axis=1)
    if model == 2:  # Quad
        A = np.concatenate((A, (imdates_years ** 2)[:, np.newaxis]), axis=1)
        An = np.concatenate((An, (xvalues_years ** 2)[:, np.newaxis]), axis=1)
    if model == 3:  # Annual+Q
        sin = np.sin(2 * np.pi * imdates_years)
        cos = np.cos(2 * np.pi * imdates_years)
        A = np.concatenate((A, (imdates_years ** 2)[:, np.newaxis], sin[:, np.newaxis], cos[:, np.newaxis]), axis=1)
        sin = np.sin(2 * np.pi * xvalues_years)
        cos = np.cos(2 * np.pi * xvalues_years)
        An = np.concatenate((An, (xvalues_years ** 2)[:, np.newaxis], sin[:, np.newaxis], cos[:, np.newaxis]), axis=1)

    result = sm.OLS(dph, A, missing='drop').fit()
    yvalues = result.predict(An)

    return yvalues

# path = "/home/547/co9432/PyRate/out/"
# path = "/g/data/dg9/INSAR_ANALYSIS/ORANGE/S1/PYRATE/obs/out/" # ORANGE STACK
path = "/g/data/dg9/INSAR_ANALYSIS/EROMANGA/S1/PYRATE/obs/out/"
filelist = []

# Search for cumulative displacement time series output tiff files
for file in os.listdir(path):
    if fnmatch.fnmatch(file, 'tscuml_*.tif'):
        filelist.append(file)

filelist.sort()
for i in filelist: print(i)

# pre-allocate a 3D numpy array to read the tiff raster bands in to. include first 'zero' time slice
src = rasterio.open(os.path.join(path, filelist[1]))
data = src.read()
cuml = np.zeros((len(filelist)+1, src.shape[0], src.shape[1]))

# pre-allocate first (zero) epoch
dates = [dt.strptime(filelist[1][7:17], '%Y-%m-%d')] # 1st epoch
imdates_ordinal = [dates[0].toordinal()]

# reading *tif files and generate cumulative variable
for i, file in enumerate(filelist):
    # print(i,file)
    src = rasterio.open(os.path.join(path, file))
    data = src.read()
    cuml[i+1, :, :] = np.squeeze(data, axis=(0,))
    temp = dt.strptime(src.tags()['EPOCH_DATE'], '%Y-%m-%d')
    dates.append(dt.strptime(src.tags()['EPOCH_DATE'], '%Y-%m-%d'))
    imdates_ordinal.append(temp.toordinal())

imdates_dt = dates

# calculate image bounds
bounds = src.bounds
x_coord = np.linspace(bounds[0], bounds[2], src.width)
y_coord = np.linspace(bounds[1], bounds[3], src.height)
dac = xr.DataArray(cuml, coords={'time': dates, 'lon': x_coord, 'lat': y_coord}, dims=['time', 'lat', 'lon'])
ds = xr.Dataset()
ds['tscuml'] = dac
n_im, length, width = cuml.shape

# choose final time slice
time_slice = len(dates)-1

####  ANIMATION of displacement
# import matplotlib.animation as animation
# fig = plt.figure()
# ims = []
# for ii in range(1,time_slice+1):
#     # print(ii)
#     data = ds.tscuml[ii]
#     cmap = plt.set_cmap('gist_rainbow')
#     im = plt.imshow(data, animated=True)
#     ims.append([im])

# ani = animation.ArtistAnimation(fig, ims, interval=3, blit=True,
#                                    repeat_delay=1000)
# plt.show()
#######


# Reading velocity data
src2 = rasterio.open(os.path.join(path, 'stack_rate.tif'))
vel = src2.read()
bounds2 = src2.bounds
x_coord2 = np.linspace(bounds2[0], bounds2[2], src2.width)
y_coord2 = np.linspace(bounds2[1], bounds2[3], src2.height)
dac2 = xr.DataArray(vel[0,:,:], coords={'lon': x_coord2, 'lat': y_coord2}, dims=['lat', 'lon'])
vs = xr.Dataset()
vs['vel'] = dac2

## set reference area and initial point
refx1 = int(len(x_coord2)/ 2)
refx2 = int(len(x_coord2)/ 2) + 1
refy1 = int(len(y_coord2)/ 2)
refy2 = int(len(y_coord2)/ 2) + 1

refarea = (refx1,refx2,refy1,refy2)

point_x = refx1
point_y = refy1

## Plot figure of Velocity and Cumulative displacement
# for last cum
auto_crange: float = 99.8
refvalue_lastcum = np.nanmean(cuml[-1, refy1:refy2, refx1:refx2]) # reference values
dmin_auto = np.nanpercentile((cuml[-1, :, :]), 100-auto_crange)
dmax_auto = np.nanpercentile((cuml[-1, :, :]), auto_crange)
dmin = dmin_auto - refvalue_lastcum
dmax = dmax_auto - refvalue_lastcum

#from last velocity
refvalue_vel = np.nanmean(vel[0, refy1:refy2 + 1, refx1:refx2 + 1])
vmin_auto = np.nanpercentile(vel[0, :, :], 100 - auto_crange)
vmax_auto = np.nanpercentile(vel[0, :, :], auto_crange)
vmin = vmin_auto - refvalue_vel
vmax = vmax_auto - refvalue_vel

# plotting cum disp and vel
figsize = (7,7)
pv = plt.figure('Velocity / Cumulative Displacement', figsize)
axv = pv.add_axes([0.15,0.15,0.75,0.83])
axv.set_title('Velocity')
axt2 = pv.text(0.01, 0.99, 'Left-doubleclick:\n Plot time series\nRight-drag:\n Change ref area', fontsize=8, va='top')
axt = pv.text(0.01, 0.78, 'Ref area:\n X {}:{}\n Y {}:{}\n (start from 0)'.format(refx1, refx2, refy1, refy2),
              fontsize=8, va='bottom')

cmap = plt.set_cmap('gist_rainbow')
cax = axv.imshow(vs.vel, clim=[vmin, vmax], cmap=cmap)
#cax = axv.imshow(vs.vel, cmap, alpha=1, origin='upper',extent=[vs.coords['lon'].min(), vs.coords['lon'].max(), vs.coords['lat'].min(), vs.coords['lat'].max()], clim=(-100, 100)) #for displacement
#cax = axv.imshow(ds.tscuml[1], cmap, alpha=1, origin='upper',extent=[ds.coords['lon'].min(), ds.coords['lon'].max(), ds.coords['lat'].min(), ds.coords['lat'].max()], clim=(-100, 100)) #for displacement
cbr = pv.colorbar(cax, orientation='vertical')
cbr.set_label('mm/yr')

#%% Radio buttom for velocity selection
mapdict_data = {}
mapdict_unit = {}
mapdict_vel = {'Vel': vel}
mapdict_unit.update([('Vel', 'mm/yr')])
mapdict_data = mapdict_vel  ## To move vel to top

# names = ['Vel', 'Disp']
# units = ['mm/yr', 'mm']
# mapdict_data[names[0]] = vel
# mapdict_unit[names[0]] = units[0]
# mapdict_vel = {'Vel': vel}
# mapdict_unit.update([('Vel', 'mm/yr')])
# mapdict_vel = {'Vel': vel, 'Disp': ds.tscuml}
# mapdict_unit.update([('Vel', 'mm/yr'), ('Disp', 'mm')])

axrad_vel = pv.add_axes([0.01, 0.3, 0.13, len(mapdict_data)*0.025+0.04])
### Radio buttons
radio_vel = RadioButtons(axrad_vel, tuple(mapdict_data.keys()))
for label in radio_vel.labels:
    label.set_fontsize(10)

cum_disp_flag = False
climauto = True

# %% Set ref function
def line_select_callback(eclick, erelease):
    global refx1, refx2, refy1, refy2, dmin, dmax   ## global cannot change existing values... why?

    # refx1p, refx2p, refy1p, refy2p = refx1, refx2, refy1, refy2  ## Previous
    x1, y1 = eclick.xdata, eclick.ydata
    x2, y2 = erelease.xdata, erelease.ydata

    if x1 <= x2:
        refx1, refx2 = [int(np.round(x1)), int(np.round(x2))]
    elif x1 > x2:
        refx1, refx2 = [int(np.round(x1)), int(np.round(x2))]
    if y1 <= y2:
        refy1, refy2 = [int(np.round(y1)), int(np.round(y2))]
    elif y1 > y2:
        refy1, refy2 = [int(np.round(y1)), int(np.round(y2))]

    # refx1h = refx1 - 0.5; refx2h = refx2 - 0.5  ## Shift half for plot
    # refy1h = refy1 - 0.5; refy2h = refy2 - 0.5

    axt.set_text('Ref area:\n X {}:{}\n Y {}:{}\n (start from 0)'.format(refx1, refx2, refy1, refy2))
    # rax.set_data([refx1h, refx2h, refx2h, refx1h, refx1h], [refy1h, refy1h, refy2h, refy2h, refy1h])
    pv.canvas.draw()

    ### Change clim
    if climauto:  ## auto
        refvalue_lastcum = np.nanmean(cuml[-1, refy1:refy2, refx1:refx2])  # reference values
        dmin = dmin_auto - refvalue_lastcum
        dmax = dmax_auto - refvalue_lastcum

    ### Update draw
    if not cum_disp_flag:  ## vel or noise indice # Chandra
        val_selected = radio_vel.value_selected
        val_ind = list(mapdict_data.keys()).index(val_selected)
        radio_vel.set_active(val_ind)
    else:  ## cumulative displacement
        time_selected = tslider.val
        tslider.set_val(time_selected)

    if lastevent:  ## Time series plot
        printcoords(lastevent)

RS = RectangleSelector(axv, line_select_callback, drawtype='box', useblit=True, button=[3], spancoords='pixels', interactive=False)

plt.connect('key_press_event', RS)
# plt.show()


vlimauto = True
#val_ind = list(mapdict_data.keys())
def show_vel(val_ind):
    global vmin, vmax, cum_disp_flag
    cum_disp_flag = False

    if 'Vel' in val_ind:  ## Velocity
        # data = mapdict_data[val_ind[0]]
        data = mapdict_data[val_ind]
        if vlimauto:  ## auto
            vmin = np.nanpercentile(data, 100 - auto_crange)
            vmax = np.nanpercentile(data, auto_crange)
        cax.set_cmap(cmap)
        cax.set_clim(vmin, vmax)
        cbr.set_label('mm/yr')

    # if 'Disp' in val_ind:
    #     data = mapdict_data[val_ind[1]][100]
    #     if vlimauto:  ## auto
    #         vmin = np.nanpercentile(data, 100 - auto_crange)
    #         vmax = np.nanpercentile(data, auto_crange)
    #     cax.set_cmap(cmap)
    #     cax.set_clim(vmin, vmax)
    #     cbr.set_label('mm/yr')

    cbr.set_label(mapdict_unit[val_ind])
    cax.set_data(data)
    axv.set_title(val_ind)
    #cax.set_clim(-100, 100)

    pv.canvas.draw()

radio_vel.on_clicked(show_vel)

# Slider for cumulative displacement
axtim = pv.add_axes([0.1, 0.08, 0.8, 0.05], yticks=[])
tslider = Slider(axtim, 'year', imdates_ordinal[0]-3, imdates_ordinal[-1]+3, valinit=imdates_ordinal[0])
tslider.ax.bar(imdates_ordinal, np.ones(len(imdates_ordinal)), facecolor='black', width=4)
tslider.ax.bar(imdates_ordinal[0], 1, facecolor='red', width=10)

loc_tslider = tslider.ax.xaxis.set_major_locator(mdates.AutoDateLocator())
try:  # Only support from Matplotlib 3.1!
    tslider.ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc_tslider))
except:
    tslider.ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m/%d'))
    for label in tslider.ax.get_xticklabels():
        label.set_rotation(20)
        label.set_horizontalalignment('right')

dstr_ref = imdates_dt[0].strftime('%Y/%m/%d') # reference image date
def tim_slidupdate(val):
    global cum_disp_flag
    timein = tslider.val
    timenearest = np.argmin(np.abs(mdates.date2num(imdates_dt) - timein))

    dstr = imdates_dt[timenearest].strftime('%Y/%m/%d')
    axv.set_title('%s (Ref: %s)' % (dstr, dstr_ref))

    newv = (cuml[timenearest, :, :])
    # newv = (cuml[timenearest, :, :])
    cax.set_data(newv)
    cax.set_cmap(cmap)
    cax.set_clim(dmin, dmax)
    # cax.set_clim(-100, 100)
    cbr.set_label('mm')
    cum_disp_flag = True

    pv.canvas.draw()

tslider.on_changed(tim_slidupdate)

# point = plt.ginput() # for selecting a point

##### Plot figure of time-series at a point
pts = plt.figure('Time-series')
axts = pts.add_axes([0.12, 0.14, 0.7, 0.8])

axts.scatter(imdates_dt, np.zeros(len(imdates_dt)), c='b', alpha=0.6)
axts.grid()

axts.set_xlabel('Time [Year]')
axts.set_ylabel('Displacement [mm]')

loc_ts = axts.xaxis.set_major_locator(mdates.AutoDateLocator())
try:  # Only support from Matplotlib 3.1
    axts.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc_ts))
except:
    axts.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m/%d'))
    for label in axts.get_xticklabels():
        label.set_rotation(20)
        label.set_horizontalalignment('right')

### Ref info at side
axtref = pts.text(0.83, 0.95, 'Ref area:\n X {}:{}\n Y {}:{}\n (start from 0)\nRef date:\n {}'.format(refx1, refx2, refy1, refy2, dstr_ref), fontsize=8, va='top')

### Fit function for time series
fitbox = pts.add_axes([0.83, 0.10, 0.16, 0.25])
models = ['Linear', 'Annual+L', 'Quad', 'Annual+Q']
visibilities = [True, False, False, False]
fitcheck = CheckButtons(fitbox, models, visibilities)

def fitfunc(label):
    index = models.index(label)
    visibilities[index] = not visibilities[index]
    lines1[index].set_visible(not lines1[index].get_visible())

    pts.canvas.draw()

fitcheck.on_clicked(fitfunc)

### First show of selected point in image window
pax, = axv.plot([point_y], [point_x], 'k', linewidth=3)
pax2, = axv.plot([point_y], [point_x], 'Pk')

### Plot time series at clicked point
lastevent = []
geocod_flag = False
# label1 = '1: No filter'
label1 = 'PyRate: tscuml '
ylen = []

def printcoords(event):
    global dph, lines1, lines2, lastevent
    # outputting x and y coords to console
    if event.inaxes != axv:
        return
    elif event.button != 1:
        return
    elif not event.dblclick:  ## Only double click
        return
    else:
        lastevent = event  ## Update last event

    ii = np.int(np.round(event.ydata))
    jj = np.int(np.round(event.xdata))

    ### Plot on image window
    ii1h = ii - 0.5; ii2h = ii + 1 - 0.5  ## Shift half for plot
    jj1h = jj - 0.5; jj2h = jj + 1 - 0.5

    pax.set_data([jj1h, jj2h, jj2h, jj1h, jj1h], [ii1h, ii1h, ii2h, ii2h, ii1h])
    pax2.set_data(jj, ii)
    pv.canvas.draw()

    axts.cla()
    axts.grid(zorder=0)
    axts.set_axisbelow(True)
    axts.set_xlabel('Time')
    axts.set_ylabel('Displacement (mm)')

    ### Get values of noise indices and incidence angle
    noisetxt = ''
    for key in mapdict_data:
        # val_temp = mapdict_data[key]
        val = mapdict_data[key][0, ii, jj]
        # val = val_temp[0,ii,jj]
        unit = mapdict_unit[key]
        if key.startswith('Vel'):  ## Not plot here
            continue
        elif key.startswith('n_') or key == 'mask':
            noisetxt = noisetxt + '{}: {:d} {}\n'.format(key, int(val), unit)
        else:
            noisetxt = noisetxt + '{}: {:.2f} {}\n'.format(key, int(val), unit)

    try:  # Only support from Matplotlib 3.1!
        axts.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc_ts))
    except:
        axts.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m/%d'))
        for label in axts.get_xticklabels():
            label.set_rotation(20)
            label.set_horizontalalignment('right')

    ### If not masked
    ### cumfile
    vel1p = vel[0, ii, jj] #- np.nanmean((vel[0,refy1:refy2, refx1:refx2]))
    dph = cuml[:,ii,jj]

    ## fit function
    lines1 = [0, 0, 0, 0]
    xvalues = np.arange(imdates_ordinal[0], imdates_ordinal[-1], 10)
    for model, vis in enumerate(visibilities):
        yvalues = calc_model(dph, imdates_ordinal, xvalues, model)
        lines1[model], = axts.plot(xvalues, yvalues, 'r-', visible=vis, alpha=0.6, zorder=3)

    # axts.scatter(imdates_dt, dph, label=label1, c='b', alpha=0.6, zorder=5)
    axts.scatter(imdates_ordinal, dph, label=label1, c='b', alpha=0.6, zorder=5)
    axts.set_title('vel = {:.1f} mm/yr @({}, {})'.format(vel1p, jj, ii), fontsize=10)
    # axts.set_ylim(-100,100) # Chandra added

    ### Y axis
    if ylen:
        vlim = [np.nanmedian(dph) - ylen / 2, np.nanmedian(dph) + ylen / 2]
        axts.set_ylim(vlim)

    ### Legend
    axts.legend()

    pts.canvas.draw()


#%% First show of time series window
event = matplotlib.backend_bases.LocationEvent
event.xdata = point_x
event.ydata = point_y
event.inaxes = axv
event.button = 1
event.dblclick = True
lastevent = event
printcoords(lastevent)


#%% Final linking of the canvas to the plots.
cid = pv.canvas.mpl_connect('button_press_event', printcoords)
with warnings.catch_warnings(): ## To silence user warning
    warnings.simplefilter('ignore', UserWarning)
    plt.show()
pv.canvas.mpl_disconnect(cid)

#####################





