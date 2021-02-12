#   This Python module is part of the PyRate software package.
#
#   Copyright 2020 Geoscience Australia
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
# coding: utf-8
"""
This Python module runs the main PyRate correction workflow
"""
import shutil
import os
from pathlib import Path
import pickle as cp
from typing import List

import pyrate.constants
from pyrate.core import (shared, algorithm, mpiops)
from pyrate.core.aps import wrap_spatio_temporal_filter
from pyrate.core.covariance import maxvar_vcm_calc_wrapper
from pyrate.core.mst import mst_calc_wrapper
from pyrate.core.orbital import orb_fit_calc_wrapper
from pyrate.core.dem_error import dem_error_calc_wrapper
from pyrate.core.phase_closure.closure_check import filter_to_closure_checked_ifgs, detect_pix_with_unwrapping_errors
from pyrate.core.ref_phs_est import ref_phase_est_wrapper
from pyrate.core.refpixel import ref_pixel_calc_wrapper
from pyrate.core.shared import PrereadIfg, get_tiles, mpi_vs_multiprocess_logging, join_dicts
from pyrate.core.logger import pyratelogger as log
from pyrate.configuration import Configuration, MultiplePaths, ConfigException

MAIN_PROCESS = 0


def _create_ifg_dict(params):
    """
    1. Convert ifg phase data into numpy binary files.
    2. Save the preread_ifgs dict with information about the ifgs that are
    later used for fast loading of Ifg files in IfgPart class

    :param list dest_tifs: List of destination tifs
    :param dict params: Config dictionary
    :param list tiles: List of all Tile instances

    :return: preread_ifgs: Dictionary containing information regarding
                interferograms that are used later in workflow
    :rtype: dict
    """
    dest_tifs = [ifg_path for ifg_path in params[pyrate.constants.INTERFEROGRAM_FILES]]
    ifgs_dict = {}
    process_tifs = mpiops.array_split(dest_tifs)
    for d in process_tifs:
        ifg = shared._prep_ifg(d.sampled_path, params)
        ifgs_dict[d.tmp_sampled_path] = PrereadIfg(
            path=d.sampled_path,
            tmp_path=d.tmp_sampled_path,
            nan_fraction=ifg.nan_fraction,
            first=ifg.first,
            second=ifg.second,
            time_span=ifg.time_span,
            nrows=ifg.nrows,
            ncols=ifg.ncols,
            metadata=ifg.meta_data
        )
        ifg.close()
    ifgs_dict = join_dicts(mpiops.comm.allgather(ifgs_dict))

    ifgs_dict = mpiops.run_once(__save_ifgs_dict_with_headers_and_epochs, dest_tifs, ifgs_dict, params, process_tifs)

    params[pyrate.constants.PREREAD_IFGS] = ifgs_dict
    log.debug('Finished converting phase_data to numpy in process {}'.format(mpiops.rank))
    return ifgs_dict


def __save_ifgs_dict_with_headers_and_epochs(dest_tifs, ifgs_dict, params, process_tifs):
    tmpdir = params[pyrate.constants.TMPDIR]
    if not os.path.exists(tmpdir):
        shared.mkdir_p(tmpdir)

    preread_ifgs_file = Configuration.preread_ifgs(params)
    nifgs = len(dest_tifs)
    # add some extra information that's also useful later
    gt, md, wkt = shared.get_geotiff_header_info(process_tifs[0].tmp_sampled_path)
    epochlist = algorithm.get_epochs(ifgs_dict)[0]
    log.info('Found {} unique epochs in the {} interferogram network'.format(len(epochlist.dates), nifgs))
    ifgs_dict['epochlist'] = epochlist
    ifgs_dict['gt'] = gt
    ifgs_dict['md'] = md
    ifgs_dict['wkt'] = wkt
    # dump ifgs_dict file for later use
    cp.dump(ifgs_dict, open(preread_ifgs_file, 'wb'))

    for k in ['gt', 'epochlist', 'md', 'wkt']:
        ifgs_dict.pop(k)

    return ifgs_dict


def _copy_mlooked(params):
    log.info("Copying input files into tempdir for manipulation during 'correct' steps")
    mpaths = params[pyrate.constants.INTERFEROGRAM_FILES]
    process_mpaths = mpiops.array_split(mpaths)
    for p in process_mpaths:
        shutil.copy(p.sampled_path, p.tmp_sampled_path)
        Path(p.tmp_sampled_path).chmod(0o664)  # assign write permission as prepifg output is readonly


def main(config):
    """
    Top level function to perform PyRate workflow on given interferograms

    :param dict params: Dictionary of configuration parameters

    :return: refpt: tuple of reference pixel x and y position
    :rtype: tuple
    :return: maxvar: array of maximum variance values of interferograms
    :rtype: ndarray
    :return: vcmt: Variance-covariance matrix array
    :rtype: ndarray
    """
    params = config.__dict__
    mpi_vs_multiprocess_logging("correct", params)

    # Make a copy of the multi-looked files for manipulation during correct steps
    _copy_mlooked(params)

    return correct_ifgs(config)


def _update_params_with_tiles(params: dict) -> None:
    ifg_path = params[pyrate.constants.INTERFEROGRAM_FILES][0].sampled_path
    rows, cols = params["rows"], params["cols"]
    tiles = mpiops.run_once(get_tiles, ifg_path, rows, cols)
    # add tiles to params
    params[pyrate.constants.TILES] = tiles


def update_params_with_closure_checked_ifg_list(params: dict, config: Configuration):
    if not params[pyrate.constants.PHASE_CLOSURE]:
        log.info("Phase closure correction is not required!")
        return

    ifg_files, ifgs_breach_count, num_occurences_each_ifg = filter_to_closure_checked_ifgs(config)
    if ifg_files is None:
        import sys
        sys.exit("Zero loops are returned after phase clouser calcs!!! \n"
                 "Check your phase closure configuration!")

    def _filter_to_closure_checked_multiple_paths(multi_paths: List[MultiplePaths]) -> List[MultiplePaths]:
        filtered_multi_paths = []
        for m_p in multi_paths:
            if m_p.tmp_sampled_path in ifg_files:
                filtered_multi_paths.append(m_p)
        return filtered_multi_paths

    params[pyrate.constants.INTERFEROGRAM_FILES] = \
        mpiops.run_once(_filter_to_closure_checked_multiple_paths, params[pyrate.constants.INTERFEROGRAM_FILES])

    if mpiops.rank == 0:
        with open(config.phase_closure_filtered_ifgs_list(params), 'w') as f:
            lines = [p.converted_path + '\n' for p in params[pyrate.constants.INTERFEROGRAM_FILES]]
            f.writelines(lines)

    # insert nans where phase unwrap threshold is breached
    if mpiops.rank == 0:
        detect_pix_with_unwrapping_errors(ifgs_breach_count, num_occurences_each_ifg, params)

    _create_ifg_dict(params)

    return params


correct_steps = {
    'orbfit': orb_fit_calc_wrapper,
    'refphase': ref_phase_est_wrapper,
    'phase_closure': update_params_with_closure_checked_ifg_list,
    'demerror': dem_error_calc_wrapper,
    'mst': mst_calc_wrapper,
    'apscorrect': wrap_spatio_temporal_filter,
    'maxvar': maxvar_vcm_calc_wrapper,
}


def correct_ifgs(config: Configuration) -> None:
    """
    Top level function to perform PyRate workflow on given interferograms
    """
    params = config.__dict__
    __validate_correct_steps(params)

    # house keeping
    _update_params_with_tiles(params)
    _create_ifg_dict(params)
    params[pyrate.constants.REFX_FOUND], params[pyrate.constants.REFY_FOUND] = ref_pixel_calc_wrapper(params)

    # run through the correct steps in user specified sequence
    for step in params['correct']:
        if step == 'phase_closure':
            correct_steps[step](params, config)
        else:
            correct_steps[step](params)
    log.info("Finished 'correct' step")


def __validate_correct_steps(params):
    for step in params['correct']:
        if step not in correct_steps.keys():
            raise ConfigException(f"{step} is not a supported 'correct' step. \n"
                                  f"Supported steps are {correct_steps.keys()}")
