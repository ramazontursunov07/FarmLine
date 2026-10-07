import { useState } from 'react';
import api from '../api/axios';

function FarmForm({ onFarmCreated }) {
    const [formData, setFormData] = useState({
        name: '',
        location: '',
        farm_type: 'chorvachilik',
    });
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleChange = (e) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const response = await api.post('farms/', formData);
            onFarmCreated(response.data);
            setFormData({ name: '', location: '', farm_type: 'chorvachilik' });
        } catch (err) {
            setError('Ferma yaratishda xatolik yuz berdi');
        } finally {
            setLoading(false);
        }
    };

    return (
        <form className="farm-form" onSubmit={handleSubmit}>
            <h3>Yangi ferma qo'shish</h3>
            <div className="form-field">
                <label>Nomi</label>
                <input
                    type="text"
                    name="name"
                    value={formData.name}
                    onChange={handleChange}
                    required
                />
            </div>
            <div className="form-field">
                <label>Joylashuvi</label>
                <input
                    type="text"
                    name="location"
                    value={formData.location}
                    onChange={handleChange}
                    required
                />
            </div>
            <div className="form-field">
                <label>Turi</label>
                <select
                    name="farm_type"
                    value={formData.farm_type}
                    onChange={handleChange}
                >
                    <option value="chorvachilik">Chorvachilik</option>
                    <option value="parrandachilik">Parrandachilik</option>
                    <option value="aralash">Aralash</option>
                </select>
            </div>
            {error && <p className="error-text">{error}</p>}
            <button type="submit" className="btn-primary" disabled={loading}>
                {loading ? 'Kuting...' : 'Qo\'shish'}
            </button>
        </form>
    );
}

export default FarmForm;
