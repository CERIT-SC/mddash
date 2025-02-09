import { useSearchParams } from 'react-router-dom';

import CustomStepper from '../components/Stepper'


const Wizard = () => {
    const [searchParams] = useSearchParams();
    const id = searchParams.get('id');

    return (
        <div>
            <h1>Wizard</h1>
            <p>Wizard ID: {id}</p>

            <CustomStepper />
        </div>
    )
}

export default Wizard
