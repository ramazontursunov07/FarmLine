import { useState } from 'react';
import api from '../api/axios';
import { t } from '../i18n';

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
            setError(t('Ferma yaratishda xatolik yuz berdi'));
        } finally {
            setLoading(false);
        }
    };

    return (
        <form className="farm-form" onSubmit={handleSubmit}>
            <h3>{t("Yangi ferma qo'shish")}</h3>
            <div className="form-field">
                <label>{t('Nomi')}</label>
                <input
                    type="text"
                    name="name"
                    value={formData.name}
                    onChange={handleChange}
                    required
                />
            </div>
            <div className="form-field">
                <label>{t('Joylashuvi')}</label>
                <input
                    type="text"
                    name="location"
                    value={formData.location}
                    onChange={handleChange}
                    required
                />
            </div>
            <div className="form-field">
                <label>{t('Turi')}</label>
                <select
                    name="farm_type"
                    value={formData.farm_type}
                    onChange={handleChange}
                >
                    <option value="chorvachilik">{t('Chorvachilik')}</option>
                    <option value="parrandachilik">{t('Parrandachilik')}</option>
                    <option value="aralash">{t('Aralash')}</option>
                </select>
            </div>
            {error && <p className="error-text">{error}</p>}
            <button type="submit" className="btn-primary" disabled={loading}>
                {loading ? t('Kuting...') : t("Qo'shish")}
            </button>
        </form>
    );
}

export default FarmForm;
