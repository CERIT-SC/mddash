import axios, { AxiosResponse } from 'axios';

import { API_BASE } from './const';
import { Experiment, FileOption, GromacsJob, NotebookStatus, ResourceUsage, TunerStatus } from './types'


interface ApiData<T = any> {
    data: T | null;
    error: string | null;
}


/**
 * Handle response from axios request with error handling
 * 
 * @param request - axios request promise
 * @param fallbackMsg - message to return if request fails
 * @returns Object with data and error fields
 */
const handle_request = async <T = any>(
    request: Promise<AxiosResponse>, 
    fallbackMsg: string
): Promise<ApiData<T>> => {
    try {
        const response = await request;
        const errMsg = response.data.success
            ? null
            : response.data.message || fallbackMsg;
        const data = response.data.data || null;
        return { data: data, error: errMsg };
    } catch (error) {
        return { data: null, error: fallbackMsg };
    }
}


// ----- Experiment -----

export const get_experiments = async (): Promise<ApiData<Experiment[]>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments`),
        'Failed to fetch experiments.'
    )
}

export const get_experiment = async (id: string): Promise<ApiData<Experiment>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}`),
        'Failed to fetch experiment.'
    )
}

export const create_experiment = async (formData: FormData): Promise<ApiData<Experiment>> => {
    return await handle_request(
        axios.post(`${API_BASE}/experiments`, formData),
        'Failed to create experiment.'
    )
}

export const delete_experiment = async (id: string): Promise<ApiData<null>> => {
    return await handle_request(
        axios.delete(`${API_BASE}/experiments/${id}`),
        'Failed to delete experiment.'
    )
}


// ----- Notebook -----

export const get_notebook = async (id: string): Promise<ApiData<NotebookStatus>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/notebook`),
        'Failed to fetch notebook.'
    )
}

export const spawn_notebook = async (id: string): Promise<ApiData<NotebookStatus>> => {
    return await handle_request(
        axios.post(`${API_BASE}/experiments/${id}/notebook`),
        'Failed to spawn notebook.'
    )
}

export const delete_notebook = async (id: string): Promise<ApiData<null>> => {
    return await handle_request(
        axios.delete(`${API_BASE}/experiments/${id}/notebook`),
        'Failed to delete notebook.'
    )
}


// ----- Tuner -----

export const tuner_statuses = async (id: string): Promise<ApiData<Record<string, TunerStatus>>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/tuner`),
        'Failed to fetch tuner statuses.'
    )
}

export const tuner_status = async (id: string, tprName: string): Promise<ApiData<TunerStatus>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/tuner/${tprName}`),
        'Failed to fetch tuner status.'
    )
}

export const run_tuner = async (id: string, tprName: string): Promise<ApiData<TunerStatus>> => {
    return await handle_request(
        axios.post(`${API_BASE}/experiments/${id}/tuner/${tprName}`),
        'Failed to run tuner.'
    )
}

export const delete_tuner = async (id: string, tprName: string): Promise<ApiData<null>> => {
    return await handle_request(
        axios.delete(`${API_BASE}/experiments/${id}/tuner/${tprName}`),
        'Failed to kill tuner.'
    )
}


// ----- Gromacs -----

export const submit_gmx = async (id: string, tprName: string, formData: FormData): Promise<ApiData<GromacsJob>> => {
    return await handle_request(
        axios.post(`${API_BASE}/experiments/${id}/gmx/${tprName}`, formData),
        'Failed to submit Gromacs job.'
    )
}

export const gmx_statuses = async (id: string): Promise<ApiData<Record<string, GromacsJob>>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/gmx`),
        'Failed to fetch Gromacs statuses.'
    )
}

export const gmx_status = async (id: string, tprName: string): Promise<ApiData<GromacsJob>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/gmx/${tprName}`),
        'Failed to fetch Gromacs status.'
    )
}

export const delete_gmx = async (id: string, tprName: string): Promise<ApiData<null>> => {
    return await handle_request(
        axios.delete(`${API_BASE}/experiments/${id}/gmx/${tprName}`),
        'Failed to delete Gromacs job.'
    )
}


// ----- Files -----

export const find_files = async (id: string, extension: string): Promise<ApiData<FileOption[]>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/files?ext=${extension}`),
        'Failed to find files.'
    )
}

export const get_file = async (id: string, path: string): Promise<ApiData<File>> => {
    try {
        const response = await axios.get(`${API_BASE}/experiments/${id}/files/${path}`, {
            responseType: 'blob' // Ensure the response is treated as a file
        });
        const file = new File([response.data], path, { type: response.headers['content-type'] });
        return { data: file, error: null };
    } catch (error) {
        return { data: null, error: 'Failed to fetch file.' };
    }
}


// ----- Other -----

export const publish_experiment = async (id: string): Promise<ApiData<any>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/publish`),
        'Failed to publish experiment.'
    )
}

export const get_metrics = async (): Promise<ApiData<ResourceUsage>> => {
    return await handle_request(
        axios.get(`${API_BASE}/metrics`),
        'Failed to fetch metrics.'
    )
}
