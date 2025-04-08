import axios, { AxiosResponse } from 'axios';

import { API_BASE } from './const';


interface ApiData {
    data: any;
    error: string | null;
}


/**
 * Handle response from axios request with error handling
 * 
 * @param request - axios request promise
 * @param fallbackMsg - message to return if request fails
 * @returns Object with data and error fields
 */
const handle_request = async (request: Promise<AxiosResponse>, fallbackMsg: string): Promise<ApiData> => {
    try {
        const response = await request;
        const errMsg = response.data.status === 'error' 
            ? response.data.message || fallbackMsg 
            : null;

        return { data: response.data, error: errMsg };
    } catch (error) {
        return { data: null, error: fallbackMsg };
    }
}


export const get_experiments = async () => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments`),
        'Failed to fetch experiments.'
    )
}


export const get_experiment = async (id: string) => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}`),
        'Failed to fetch experiment.'
    )
}


export const create_experiment = async (formData: FormData) => {
    return await handle_request(
        axios.post(`${API_BASE}/experiments`, formData),
        'Failed to create experiment.'
    )
}


export const delete_experiment = async (id: string) => {
    return await handle_request(
        axios.delete(`${API_BASE}/experiments/${id}`),
        'Failed to delete experiment.'
    )
}


export const get_notebook = async (id: string) => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/notebook`),
        'Failed to fetch notebook.'
    )
}


export const spawn_notebook = async (id: string) => {
    return await handle_request(
        axios.post(`${API_BASE}/experiments/${id}/notebook`),
        'Failed to spawn notebook.'
    )
}


export const delete_notebook = async (id: string) => {
    return await handle_request(
        axios.delete(`${API_BASE}/experiments/${id}/notebook`),
        'Failed to delete notebook.'
    )
}


export const tuner_status = async (id: string) => {
    return await handle_request(
        axios.get(`${API_BASE}/experiments/${id}/tuner`),
        'Failed to fetch tuner status.'
    )
}

export const run_tuner = async (id: string) => {
    return await handle_request(
        axios.post(`${API_BASE}/experiments/${id}/tuner`),
        'Failed to run tuner.'
    )
}
