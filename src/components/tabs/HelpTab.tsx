import { t } from '../../i18n';

export default function HelpTab() {
  return (
    <div className="help-container">
      <h2>{t('help.columns')}</h2>
      <p><strong>VFR</strong> {t('help.vfr_desc')}</p>
      <p><strong>VMAF</strong> {t('help.vmaf_desc')}</p>
      <p><strong>CRF</strong> {t('help.crf_desc')}</p>

      <h2>{t('help.red_title')}</h2>
      <p>{t('help.red_est_size')}</p>
      <p>{t('help.red_crf')}</p>

      <h2>{t('help.params_title')}</h2>
      <p><strong>{t('help.codec_label')}</strong> {t('help.codec_desc')}</p>
      <p><strong>{t('help.preset_label')}</strong> {t('help.preset_desc')}</p>
      <p><strong>{t('help.coding_label')}</strong> {t('help.coding_desc')}</p>

      <h2>{t('help.auto_title')}</h2>
      <p>{t('help.auto_desc')}</p>
      <p>{t('help.auto_how')}</p>
      <ul>
        <li>{t('help.auto_how_1')}</li>
        <li>{t('help.auto_how_2')}</li>
        <li>{t('help.auto_how_3')}</li>
      </ul>

      <h2>{t('help.skip_title')}</h2>
      <p>{t('help.skip_desc')}</p>
      <ul>
        <li>{t('help.skip_min_size')}</li>
        <li>{t('help.skip_crf_ge')}</li>
      </ul>
      <p>{t('help.skip_reported')}</p>

      <h2>{t('help.support_title')}</h2>
      <p>{t('help.support_desc')}</p>
      <p>
        <a
          href="https://interesting-knowledges.vercel.app/docs/otblagodarit-avtora.-pomosch-proektam"
          target="_blank"
          rel="noopener noreferrer"
        >
          {t('help.support_link')}
        </a>
      </p>
    </div>
  );
}
