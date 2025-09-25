import axios, { AxiosResponse } from 'axios';

import { API_BASE } from './const';
import { Experiment, FileOption, GromacsJob, Notebook, ResourceUsage, TunerJob } from './types'


interface ApiData<T> {
    data: T | null;
    error: string | null;
}


const parseResponse = <T>(response: AxiosResponse, fallbackMsg: string): ApiData<T> => {
    const errMsg = response.data.success
        ? null
        : response.data.message || fallbackMsg;
    const data = response.data.data;
    return { data: data, error: errMsg };
};

const handle_request = async <T>(
    request: Promise<AxiosResponse>, 
    fallbackMsg: string
): Promise<ApiData<T>> => {
    try {
        const response = await request;
        return parseResponse<T>(response, fallbackMsg);
    } catch (error) {
        if (axios.isAxiosError(error) && error.response) {
            return parseResponse<T>(error.response, fallbackMsg);
        }
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

export const publish_experiment = async (id: string): Promise<ApiData<any>> => {
    return await handle_request(
        axios.post(`${API_BASE}/experiments/${id}/publish`),
        'Failed to publish experiment.'
    )
}

export const get_experiment_step = async (id: string): Promise<ApiData<number>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/step`),
        'Failed to fetch experiment step.'
    )
}


// ----- Notebook -----

export const get_notebook = async (id: string): Promise<ApiData<Notebook>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/notebook`),
        'Failed to fetch notebook.'
    )
}

export const spawn_notebook = async (id: string): Promise<ApiData<Notebook>> => {
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

export const tuner_statuses = async (id: string): Promise<ApiData<TunerJob[]>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/tuner`),
        'Failed to fetch tuner statuses.'
    )
}

export const tuner_status = async (id: string, tprName: string): Promise<ApiData<TunerJob>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/tuner/${tprName}`),
        'Failed to fetch tuner status.'
    )
}

export const run_tuner = async (id: string, tprName: string): Promise<ApiData<TunerJob>> => {
    return await handle_request(
        axios.post(`${API_BASE}/experiments/${id}/tuner/${tprName}`),
        'Failed to run tuner.'
    )
}

export const stop_tuner = async (id: string, tprName: string): Promise<ApiData<null>> => {
    return await handle_request(
        axios.post(`${API_BASE}/experiments/${id}/tuner/${tprName}/stop`),
        'Failed to stop tuner.'
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

export const gmx_statuses = async (id: string): Promise<ApiData<GromacsJob[]>> => {
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

export const gmx_logs = async (id: string, tprName: string, type: 'gmx' | 'stdout' | 'stderr', tail: number): Promise<ApiData<string>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/gmx/${tprName}/log`, {
            params: { type, tail }
        }),
        'Failed to fetch Gromacs logs.'
    )
}


// ----- Files -----

export const find_files = async (id: string, extension: string | string[]): Promise<ApiData<FileOption[]>> => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/files`, {
            params: { ext: extension instanceof Array ? extension.join(',') : extension }
        }),
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


// ----- Metrics -----

export const get_metrics = async (): Promise<ApiData<ResourceUsage>> => {
    return await handle_request(
        axios.get(`${API_BASE}/metrics`),
        'Failed to fetch metrics.'
    )
}
